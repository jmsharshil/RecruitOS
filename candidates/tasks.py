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
def simulate_client_submission_email(application_id, client_email):
    logger.info(f"[SIMULATION] Profile submission email sent for application {application_id} to client {client_email}")

@run_in_thread
def simulate_interview_reminder(interview_schedule_id):
    try:
        schedule = InterviewSchedule.objects.select_related(
            'application__candidate', 'application__job'
        ).get(id=interview_schedule_id)
        application = schedule.application
        candidate = application.candidate
        for recruiter in application.job.assigned_recruiters.all():
            Notification.objects.create(
                user=recruiter,
                organization=application.organization,
                title="Interview Reminder",
                message=f"Interview for {candidate.candidate_name} is in 24 hours.",
                type='warning',
                link=f"/candidates/{candidate.id}"
            )
        logger.info(f"[SIMULATION] Interview reminder fired for schedule {interview_schedule_id}")
    except InterviewSchedule.DoesNotExist:
        pass

@run_in_thread
def simulate_resume_submission_notification(obj_id):
    """Notify about new resume submission. Supports Application (job-specific) or pure pool Candidate (obj_id = candidate.id)."""
    try:
        application = Application.objects.select_related('candidate', 'job').get(id=obj_id)
        candidate = application.candidate
        for recruiter in application.job.assigned_recruiters.all():
            Notification.objects.create(
                user=recruiter,
                organization=application.organization,
                title="New Resume Submitted",
                message=f"{candidate.candidate_name} submitted a resume for '{application.job.title}'.",
                type='info',
                link=f"/candidates/{candidate.id}"
            )
        logger.info(f"[SIMULATION] Resume submission notification fired for application {obj_id}")
        return
    except Application.DoesNotExist:
        pass
    except Exception as e:
        logger.error(f"Notification error: {e}")
        return

    # Fallback for pure pool candidates (no Application)
    try:
        candidate = Candidate.objects.get(id=obj_id, is_deleted=False)
        for recruiter in User.objects.filter(
            organization=candidate.organization, 
            role=UserRole.RECRUITER,
            is_active=True
        ):
            Notification.objects.create(
                user=recruiter,
                organization=candidate.organization,
                title="New Resume in Pool",
                message=f"{candidate.candidate_name} added to talent pool.",
                type='info',
                link=f"/candidates/{candidate.id}"
            )
        logger.info(f"[SIMULATION] Resume submission notification fired for pool candidate {obj_id}")
    except Candidate.DoesNotExist:
        logger.warning(f"No Application or Candidate found for id={obj_id}")
    except Exception as e:
        logger.error(f"Pool notification error: {e}")
