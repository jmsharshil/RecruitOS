import logging
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from django.utils import timezone
from candidates.models import InterviewSchedule
from accounts.email_utils import send_org_email
from collections import defaultdict
from django.conf import settings

logger = logging.getLogger(__name__)

def send_daily_interview_reminders():
    try:
        ist_tz = pytz.timezone('Asia/Kolkata')
        today = timezone.localdate(timezone=ist_tz)
        logger.info(f"Running daily interview reminders for {today}")
        
        interviews_today = InterviewSchedule.objects.filter(
            date=today,
            is_deleted=False,
            application__is_deleted=False
        ).select_related(
            'application__candidate', 
            'application__job',
            'application__job__created_by',
            'application__created_by', 
            'application__candidate__uploaded_by',
            'organization'
        ).order_by('time')

        if not interviews_today.exists():
            logger.info("No interviews scheduled for today.")
            return

        interviews_by_user_and_creator = defaultdict(list)
        for interview in interviews_today:
            app = interview.application
            worker = app.created_by or app.candidate.uploaded_by
            job_creator = app.job.created_by
            if worker and worker.email:
                interviews_by_user_and_creator[(worker, job_creator)].append(interview)

        frontend_base = getattr(settings, 'FRONTEND_URL', getattr(settings, 'FRONTEND_BASE_URL', 'https://recruitos.jmstech.co'))

        for (user, job_creator), interviews in interviews_by_user_and_creator.items():
            try:
                org = interviews[0].organization
                
                message_lines = []
                for interview in interviews:
                    candidate_name = interview.application.candidate.candidate_name
                    job_title = interview.application.job.title
                    time_str = interview.time.strftime('%I:%M %p') if interview.time else 'Time not specified'
                    mode = interview.mode.title()
                    message_lines.append(f"- {time_str} : {candidate_name} for {job_title} ({mode})")
                    
                interview_details = "\n".join(message_lines)
                
                context = {
                    'recruiter_name': user.name,
                    'plain_message': f"You have {len(interviews)} interview(s) scheduled for today:\n\n{interview_details}\n\nPlease review your dashboard for full details: {frontend_base}"
                }
                
                from_email = job_creator.email if job_creator and job_creator.email else None
                
                send_org_email(
                    organization=org,
                    subject=f"Daily Reminder: You have {len(interviews)} interview(s) today",
                    template_name='generic_email',
                    context=context,
                    recipient_list=[user.email],
                    from_email_override=from_email
                )
                logger.info(f"Sent reminder to {user.email} for {len(interviews)} interview(s).")
                
            except Exception as e:
                logger.error(f"Failed to send daily interview reminder to {user.email}: {e}")
                
    except Exception as e:
        logger.error(f"Error in send_daily_interview_reminders job: {e}")

def start_scheduler():
    ist_tz = pytz.timezone('Asia/Kolkata')
    scheduler = BackgroundScheduler(timezone=ist_tz)
    # Schedule the job to run daily at 10:00 AM IST
    scheduler.add_job(send_daily_interview_reminders, 'cron', hour=10, minute=0)
    scheduler.start()
    logger.info("APScheduler started: Daily interview reminder scheduled for 10:00 AM IST.")
