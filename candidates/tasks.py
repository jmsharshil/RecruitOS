import logging
import threading
from notifications.models import Notification
from candidates.models import InterviewSchedule, Candidate

logger = logging.getLogger(__name__)

def run_in_thread(func):
    def wrapper(*args, **kwargs):
        thread = threading.Thread(target=func, args=args, kwargs=kwargs)
        thread.start()
        return thread
    return wrapper

@run_in_thread
def simulate_client_submission_email(candidate_id, client_email):
    logger.info(f"[SIMULATION] Profile submission email sent for candidate {candidate_id} to client {client_email}")

@run_in_thread
def simulate_interview_reminder(interview_schedule_id):
    try:
        schedule = InterviewSchedule.objects.select_related('candidate__job').get(id=interview_schedule_id)
        candidate = schedule.candidate
        for recruiter in candidate.job.assigned_recruiters.all():
            Notification.objects.create(
                user=recruiter,
                title="Interview Reminder",
                message=f"Interview for {candidate.candidate_name} is in 24 hours.",
                type='warning',
                link=f"/candidates/{candidate.id}"
            )
        logger.info(f"[SIMULATION] Interview reminder fired for schedule {interview_schedule_id}")
    except InterviewSchedule.DoesNotExist:
        pass

@run_in_thread
def simulate_resume_submission_notification(candidate_id):
    try:
        candidate = Candidate.objects.select_related('job').get(id=candidate_id)
        for recruiter in candidate.job.assigned_recruiters.all():
            Notification.objects.create(
                user=recruiter,
                title="New Resume Submitted",
                message=f"{candidate.candidate_name} submitted a resume for '{candidate.job.title}'.",
                type='info',
                link=f"/candidates/{candidate_id}"
            )
        logger.info(f"[SIMULATION] Resume submission notification fired for candidate {candidate_id}")
    except Candidate.DoesNotExist:
        pass
