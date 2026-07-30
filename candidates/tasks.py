import logging
import threading
from notifications.models import Notification
from candidates.models import InterviewSchedule, Candidate, Application
from accounts.models import User, UserRole

logger = logging.getLogger(__name__)

def run_in_thread(func):
    def wrapper(*args, **kwargs):
        thread = threading.Thread(target=func, args=args, kwargs=kwargs)
        thread.start()
        return thread
    return wrapper

@run_in_thread
def simulate_client_submission_email(application_id, client_email, recipient_name=None):
    """Send a real (or simulated) client submission email using org branding."""
    try:
        application = Application.objects.select_related(
            'candidate', 'job', 'job__client', 'client_submission__sent_by'
        ).get(id=application_id)
        candidate = application.candidate
        org = application.organization

        if not recipient_name:
            recipient_name = application.job.client.company_name if application.job.client else client_email

        from accounts.email_utils import send_org_email
        context = {
            'client_name': recipient_name,
            'job_title': application.job.title,
            'candidate_name': candidate.candidate_name,
            'current_profile': candidate.current_profile,
            'experience': candidate.experience,
            'current_location': candidate.current_location,
            'current_ctc': application.current_ctc,
            'expected_ctc': application.expected_ctc,
            'notice_period': application.notice_period,
            'sent_by': getattr(application, 'client_submission', None) and
                       getattr(application.client_submission.sent_by, 'name', 'RecruitOS'),
            'resume_link': '',  # Set to actual resume URL when hosted
            'plain_message': f"Please find attached the profile of {candidate.candidate_name} for {application.job.title}.",
        }
        send_org_email(
            organization=org,
            subject=f"Candidate Profile: {candidate.candidate_name} — {application.job.title}",
            template_name='client_submission',
            context=context,
            recipient_list=[client_email],
        )
        logger.info(f"Client submission email sent for application {application_id} to {client_email}")
    except Exception as e:
        logger.error(f"Client submission email failed for application {application_id}: {e}")


@run_in_thread
def simulate_interview_reminder(interview_schedule_id):
    """Send interview reminder notification (in-app) + email via org SMTP."""
    try:
        schedule = InterviewSchedule.objects.select_related(
            'application__candidate', 'application__job', 'organization'
        ).get(id=interview_schedule_id)
        application = schedule.application
        candidate = application.candidate
        org = application.organization

        # In-app notifications for all assigned recruiters
        for recruiter in application.job.assigned_recruiters.all():
            Notification.objects.create(
                user=recruiter,
                organization=org,
                title="Interview Reminder",
                message=f"Interview for {candidate.candidate_name} is in 24 hours.",
                type='warning',
                link=f"/candidates/{candidate.id}"
            )

            # Also send email reminder
            try:
                from accounts.email_utils import send_org_email
                context = {
                    'recruiter_name': recruiter.name,
                    'candidate_name': candidate.candidate_name,
                    'job_title': application.job.title,
                    'interview_date': str(schedule.date),
                    'interview_time': str(schedule.time),
                    'interview_mode': schedule.mode,
                    'interviewer_name': schedule.interviewer_name,
                    'notes': schedule.notes,
                    'candidate_link': f"/candidates/{candidate.id}",
                    'plain_message': f"Reminder: Interview for {candidate.candidate_name} is scheduled for {schedule.date} at {schedule.time}.",
                }
                send_org_email(
                    organization=org,
                    subject=f"Interview Reminder: {candidate.candidate_name} — {application.job.title}",
                    template_name='interview_reminder',
                    context=context,
                    recipient_list=[recruiter.email],
                )
            except Exception as email_err:
                logger.warning(f"Interview reminder email failed for {recruiter.email}: {email_err}")

        logger.info(f"Interview reminder processed for schedule {interview_schedule_id}")
    except InterviewSchedule.DoesNotExist:
        logger.warning(f"InterviewSchedule {interview_schedule_id} not found")
    except Exception as e:
        logger.error(f"Interview reminder error: {e}")


@run_in_thread
def simulate_resume_submission_notification(obj_id):
    """Notify about new resume submission. Supports Application (job-specific) or pure pool Candidate (obj_id = candidate.id)."""
    print(f"==========> [DEBUG] simulate_resume_submission_notification called for ID: {obj_id}")
    try:
        application = Application.objects.select_related('candidate', 'job', 'job__client', 'organization').get(id=obj_id)
        candidate = application.candidate
        org = application.organization
        
        # Prepare context for the email template
        context = {
            'candidate_name': candidate.candidate_name,
            'candidate_email': candidate.email,
            'contact': candidate.contact,
            'current_profile': candidate.current_profile or 'N/A',
            'current_company': candidate.current_company or 'N/A',
            'current_location': candidate.current_location or 'N/A',
            'education': ', '.join([e.get('degree', '') if isinstance(e, dict) else str(e) for e in candidate.education]) if candidate.education and isinstance(candidate.education, list) else 'N/A',
            'skills': ', '.join(candidate.skills) if candidate.skills else 'N/A',
            'plain_message': f"A new candidate {candidate.candidate_name} has been added to your tracker."
        }
        
        from accounts.email_utils import send_org_email
        
        # Notify Recruiters
        for recruiter in application.job.assigned_recruiters.all():
            Notification.objects.create(
                user=recruiter,
                organization=org,
                title="New Resume Submitted",
                message=f"{candidate.candidate_name} submitted a resume for '{application.job.title}'.",
                type='info',
                link=f"/candidates/{candidate.id}"
            )
            # Send Email to Recruiter
            recruiter_context = context.copy()
            recruiter_context['recipient_name'] = recruiter.name
            try:
                send_org_email(
                    organization=org,
                    subject=f"Candidate Tracker Update: {candidate.candidate_name}",
                    template_name='resume_submission',
                    context=recruiter_context,
                    recipient_list=[recruiter.email],
                )
                print(f"==========> [DEBUG] EMAIL SENT TO RECRUITER: {recruiter.email}")
            except Exception as e:
                logger.error(f"Email error to recruiter: {e}")

        # Send Email to Client (if exists and has email)
        if application.job.client and application.job.client.email:
            client_context = context.copy()
            client_context['recipient_name'] = application.job.client.company_name
            try:
                send_org_email(
                    organization=org,
                    subject=f"Candidate Tracker Update: {candidate.candidate_name}",
                    template_name='resume_submission',
                    context=client_context,
                    recipient_list=[application.job.client.email],
                )
                print(f"==========> [DEBUG] EMAIL SENT TO CLIENT: {application.job.client.email}")
            except Exception as e:
                logger.error(f"Email error to client: {e}")

        logger.info(f"Resume submission notification and emails fired for application {obj_id}")
        return
    except Application.DoesNotExist:
        pass
    except Exception as e:
        logger.error(f"Notification error: {e}")
        return

    # Fallback for pure pool candidates (no Application)
    try:
        candidate = Candidate.objects.select_related('uploaded_by', 'organization').get(id=obj_id, is_deleted=False)
        org = candidate.organization
        
        context = {
            'candidate_name': candidate.candidate_name,
            'candidate_email': candidate.email,
            'contact': candidate.contact,
            'current_profile': candidate.current_profile or 'N/A',
            'current_company': candidate.current_company or 'N/A',
            'current_location': candidate.current_location or 'N/A',
            'education': ', '.join([e.get('degree', '') if isinstance(e, dict) else str(e) for e in candidate.education]) if candidate.education and isinstance(candidate.education, list) else 'N/A',
            'skills': ', '.join(candidate.skills) if candidate.skills else 'N/A',
            'plain_message': f"A new candidate {candidate.candidate_name} has been added to your pool tracker."
        }
        
        # Only notify the recruiter who uploaded it
        if candidate.uploaded_by:
            Notification.objects.create(
                user=candidate.uploaded_by,
                organization=org,
                title="New Resume in Pool",
                message=f"{candidate.candidate_name} added to talent pool.",
                type='info',
                link=f"/candidates/{candidate.id}"
            )
        else:
            print(f"==========> [DEBUG] IN-APP NOTIFICATION SKIPPED: 'uploaded_by' is empty")
                
        logger.info(f"Resume submission notification fired for pool candidate {obj_id}")
    except Candidate.DoesNotExist:
        logger.warning(f"No Application or Candidate found for id={obj_id}")
    except Exception as e:
        logger.error(f"Pool notification error: {e}")
        print(f"==========> [DEBUG] Pool notification error: {e}")
