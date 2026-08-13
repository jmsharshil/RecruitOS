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
        
        # Build dynamic tracker fields based on assigned team member format
        tracker_fields = []
        if application.job.team_member_id:
            try:
                from clients.models import TeamMemberTrackerFormat
                tracker_format = TeamMemberTrackerFormat.objects.get(
                    client_id=application.job.client_id, 
                    team_member_id=application.job.team_member_id, 
                    is_deleted=False
                )
                for col in tracker_format.columns:
                    val = ""
                    col_norm = col.strip().lower().replace(' ', '_')
                    
                    if col_norm in ['candidate_name', 'name']: val = candidate.candidate_name
                    elif col_norm == 'email': val = candidate.email
                    elif col_norm in ['phone', 'contact', 'contacts']: val = candidate.contact
                    elif col_norm in ['total_experience', 'experience', 'total_exp']: val = candidate.experience
                    elif col_norm == 'current_company': val = candidate.current_company
                    elif col_norm in ['current_designation', 'current_profile', 'designation', 'role']: val = candidate.current_profile
                    elif col_norm in ['current_ctc', 'ctc', 'cctc']: val = f"₹{application.current_ctc}" if application.current_ctc else ""
                    elif col_norm in ['expected_ctc', 'expected_ctc', 'ectc']: val = f"₹{application.expected_ctc}" if application.expected_ctc else ""
                    elif col_norm == 'notice_period': val = application.notice_period
                    elif col_norm in ['current_location', 'address', 'location']: val = candidate.current_location
                    elif col_norm == 'preferred_location': val = candidate.preferred_location
                    elif col_norm == 'hike': val = application.hike
                    elif col_norm == 'skills': val = ", ".join(candidate.skills) if isinstance(candidate.skills, list) else candidate.skills
                    elif col_norm == 'education': val = ", ".join([e.get('degree', '') if isinstance(e, dict) else str(e) for e in candidate.education]) if isinstance(candidate.education, list) else candidate.education
                    else:
                        custom_fields = application.tracker_custom_fields if isinstance(application.tracker_custom_fields, dict) else {}
                        val = custom_fields.get(col, custom_fields.get(col_norm, ""))
                    
                    if isinstance(val, str) and val.strip().lower() == "not specified":
                        val = ""
                        
                    label = col.replace('_', ' ').title()
                    tracker_fields.append({'label': label, 'value': val})
            except Exception as e:
                logger.warning(f"Could not load tracker format for team member {application.job.team_member_id}: {e}")
        
        # Fallback to standard fields if no format found
        if not tracker_fields:
            tracker_fields = [
                {'label': 'Candidate Name', 'value': candidate.candidate_name},
                {'label': 'Current Role', 'value': candidate.current_profile},
                {'label': 'Experience', 'value': candidate.experience},
                {'label': 'Location', 'value': candidate.current_location},
            ]
            if application.current_ctc: tracker_fields.append({'label': 'Current CTC', 'value': f"₹{application.current_ctc}"})
            if application.expected_ctc: tracker_fields.append({'label': 'Expected CTC', 'value': f"₹{application.expected_ctc}"})
            if application.notice_period: tracker_fields.append({'label': 'Notice Period', 'value': application.notice_period})

        context['tracker_fields'] = tracker_fields
        
        attachments = []
        if candidate.resume:
            try:
                with candidate.resume.open('rb') as f:
                    resume_content = f.read()
                import os
                resume_filename = os.path.basename(candidate.resume.name)
                mimetype = 'application/pdf' if resume_filename.lower().endswith('.pdf') else 'application/octet-stream'
                attachments.append((resume_filename, resume_content, mimetype))
            except Exception as e:
                logger.error(f"Could not read resume for client attachment: {e}")

        # print(f"==========> [DEBUG] Starting client submission email to: {client_email}")
        
        # Determine who sent it to set as the "From" address
        from_email = None
        if hasattr(application, 'client_submission') and application.client_submission.sent_by:
            from_email = application.client_submission.sent_by.email
        elif application.job.hiring_manager:
            from_email = application.job.hiring_manager.email
            
        # print(f"==========> [DEBUG] EMAIL ROUTING INFO:")
        # print(f"==========> [DEBUG]   FROM (override): {from_email or 'Default Org Email'}")
        # print(f"==========> [DEBUG]   TO (recipient): {client_email}")
        # print(f"==========> [DEBUG]   ORG: {org.name}")

        send_org_email(
            organization=org,
            subject=f"Candidate Profile: {candidate.candidate_name} — {application.job.title}",
            template_name='client_submission',
            context=context,
            recipient_list=[client_email],
            attachments=attachments,
            from_email_override=from_email
        )
        # print(f"==========> [DEBUG] Client submission email SUCCESS for application {application_id} to {client_email}")
        logger.info(f"Client submission email sent for application {application_id} to {client_email}")
    except Exception as e:
        # print(f"==========> [DEBUG] Client submission email FAILED: {e}")
        logger.error(f"Client submission email failed for application {application_id}: {e}")


@run_in_thread
def simulate_bulk_client_submission_email(application_ids, client_email, recipient_name=None):
    """Send a bulk client submission email containing a tracker of multiple candidates."""
    try:
        if not application_ids:
            return

        applications = Application.objects.select_related(
            'candidate', 'job', 'job__client', 'client_submission__sent_by', 'organization'
        ).filter(id__in=application_ids)

        if not applications.exists():
            return

        first_app = applications.first()
        org = first_app.organization
        job = first_app.job

        if not recipient_name:
            recipient_name = job.client.company_name if job.client else client_email

        from accounts.email_utils import send_org_email
        
        context = {
            'client_name': recipient_name,
            'job_title': job.title,
            'org_name': org.name,
            'sent_by': getattr(first_app, 'client_submission', None) and
                       getattr(first_app.client_submission.sent_by, 'name', 'RecruitOS') or 'RecruitOS',
        }

        # Build headers
        tracker_headers = []
        columns_to_extract = []
        
        if job.team_member_id:
            try:
                from clients.models import TeamMemberTrackerFormat
                tracker_format = TeamMemberTrackerFormat.objects.get(
                    client_id=job.client_id, 
                    team_member_id=job.team_member_id, 
                    is_deleted=False
                )
                columns_to_extract = tracker_format.columns
                tracker_headers = [col.replace('_', ' ').title() for col in columns_to_extract]
            except Exception as e:
                logger.warning(f"Could not load tracker format for team member {job.team_member_id}: {e}")

        if not tracker_headers:
            columns_to_extract = ['candidate_name', 'current_profile', 'experience', 'current_location', 'current_ctc', 'expected_ctc', 'notice_period']
            tracker_headers = ['Candidate Name', 'Current Role', 'Experience', 'Location', 'Current CTC', 'Expected CTC', 'Notice Period']

        candidates_data = []
        attachments = []

        for app in applications:
            candidate = app.candidate
            row = []
            
            for col in columns_to_extract:
                val = ""
                col_norm = col.strip().lower().replace(' ', '_')
                
                if col_norm in ['candidate_name', 'name']: val = candidate.candidate_name
                elif col_norm == 'email': val = candidate.email
                elif col_norm in ['phone', 'contact', 'contacts']: val = candidate.contact
                elif col_norm in ['total_experience', 'experience', 'total_exp']: val = candidate.experience
                elif col_norm == 'current_company': val = candidate.current_company
                elif col_norm in ['current_designation', 'current_profile', 'designation', 'role']: val = candidate.current_profile
                elif col_norm in ['current_ctc', 'ctc', 'cctc']: val = f"₹{app.current_ctc}" if app.current_ctc else ""
                elif col_norm in ['expected_ctc', 'ectc']: val = f"₹{app.expected_ctc}" if app.expected_ctc else ""
                elif col_norm == 'notice_period': val = app.notice_period
                elif col_norm in ['current_location', 'address', 'location']: val = candidate.current_location
                elif col_norm == 'preferred_location': val = candidate.preferred_location
                elif col_norm == 'hike': val = app.hike
                elif col_norm == 'skills': val = ", ".join(candidate.skills) if isinstance(candidate.skills, list) else candidate.skills
                elif col_norm == 'education': val = ", ".join([e.get('degree', '') if isinstance(e, dict) else str(e) for e in candidate.education]) if isinstance(candidate.education, list) else candidate.education
                else:
                    custom_fields = app.tracker_custom_fields if isinstance(app.tracker_custom_fields, dict) else {}
                    val = custom_fields.get(col, custom_fields.get(col_norm, ""))
                
                if isinstance(val, str) and val.strip().lower() == "not specified":
                    val = ""
                    
                row.append(val)
            
            candidates_data.append(row)

            if candidate.resume:
                try:
                    with candidate.resume.open('rb') as f:
                        resume_content = f.read()
                    import os
                    resume_filename = os.path.basename(candidate.resume.name)
                    safe_name = candidate.candidate_name.replace(' ', '_')
                    resume_filename = f"{safe_name}_{resume_filename}"
                    mimetype = 'application/pdf' if resume_filename.lower().endswith('.pdf') else 'application/octet-stream'
                    attachments.append((resume_filename, resume_content, mimetype))
                except Exception as e:
                    logger.error(f"Could not read resume for candidate {candidate.id}: {e}")

        context['tracker_headers'] = tracker_headers
        context['candidates_data'] = candidates_data

        from_email = None
        if hasattr(first_app, 'client_submission') and first_app.client_submission.sent_by:
            from_email = first_app.client_submission.sent_by.email
        elif first_app.job.hiring_manager:
            from_email = first_app.job.hiring_manager.email

        subject_count = f"{len(applications)} Candidate Profiles" if len(applications) > 1 else "1 Candidate Profile"
        
        send_org_email(
            organization=org,
            subject=f"{subject_count} for {job.title}",
            template_name='bulk_client_submission',
            context=context,
            recipient_list=[client_email],
            attachments=attachments,
            from_email_override=from_email
        )
        logger.info(f"Bulk client submission email sent for {len(applications)} apps to {client_email}")
    except Exception as e:
        logger.error(f"Bulk client submission email failed: {e}")


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
        
        manager = application.job.hiring_manager or application.job.created_by
        
        # Prepare context for the email template
        context = {
            'recipient_name': manager.name if manager else 'Manager',
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

        # Notify the Manager (Hiring Manager or the Creator of the Job)
        manager = application.job.hiring_manager or application.job.created_by
        if manager and manager.email:
            attachments = []
            if candidate.resume:
                try:
                    with candidate.resume.open('rb') as f:
                        resume_content = f.read()
                    import os
                    resume_filename = os.path.basename(candidate.resume.name)
                    # Use application/pdf for PDFs, but fallback for others
                    mimetype = 'application/pdf' if resume_filename.lower().endswith('.pdf') else 'application/octet-stream'
                    attachments.append((resume_filename, resume_content, mimetype))
                except Exception as e:
                    logger.error(f"Could not read resume for attachment: {e}")

            try:
                recruiter = application.created_by or application.candidate.uploaded_by
                from_email = recruiter.email if recruiter else None

                send_org_email(
                    organization=org,
                    subject=f"New CV Uploaded: {candidate.candidate_name} for '{application.job.title}'",
                    template_name='resume_submission',
                    context=context,
                    recipient_list=[manager.email],
                    from_email_override=from_email,
                    attachments=attachments
                )
                logger.info(f"CV review email sent to manager {manager.email} for application {obj_id}")
            except Exception as e:
                logger.error(f"Failed to send CV review email to manager: {e}")

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

@run_in_thread
def send_interview_approval_request_email(schedule_id, action_user_id=None):
    try:
        schedule = InterviewSchedule.objects.select_related('application__candidate', 'application__job', 'organization').get(id=schedule_id)
        manager = schedule.application.job.hiring_manager or schedule.application.job.created_by
        if manager and manager.email:
            from accounts.email_utils import send_org_email
            
            from_email = None
            if action_user_id:
                from accounts.models import User
                action_user = User.objects.filter(id=action_user_id).first()
                if action_user:
                    from_email = action_user.email

            context = {
                'manager_name': manager.name,
                'candidate_name': schedule.application.candidate.candidate_name,
                'job_title': schedule.application.job.title,
                'interview_date': str(schedule.date),
                'interview_time': str(schedule.time),
                'plain_message': f"An interview schedule has been proposed for {schedule.application.candidate.candidate_name}. Please review."
            }
            send_org_email(
                organization=schedule.organization,
                subject=f"Interview Schedule Approval Required: {schedule.application.candidate.candidate_name}",
                template_name='generic_email',
                context=context,
                recipient_list=[manager.email],
                from_email_override=from_email,
            )
    except Exception as e:
        logger.error(f"Failed to send interview approval request email: {e}")

@run_in_thread
def send_interview_approval_result_email(schedule_id, action_user_id=None):
    try:
        schedule = InterviewSchedule.objects.select_related('application__candidate', 'application__job', 'organization').get(id=schedule_id)
        recruiter = schedule.application.created_by or schedule.application.candidate.uploaded_by
        if recruiter and recruiter.email:
            from accounts.email_utils import send_org_email

            from_email = None
            if action_user_id:
                from accounts.models import User
                action_user = User.objects.filter(id=action_user_id).first()
                if action_user:
                    from_email = action_user.email

            context = {
                'recruiter_name': recruiter.name,
                'candidate_name': schedule.application.candidate.candidate_name,
                'status': schedule.manager_approval_status,
                'plain_message': f"The interview schedule for {schedule.application.candidate.candidate_name} has been {schedule.manager_approval_status}."
            }
            send_org_email(
                organization=schedule.organization,
                subject=f"Interview Schedule {schedule.manager_approval_status.upper()}: {schedule.application.candidate.candidate_name}",
                template_name='generic_email',
                context=context,
                recipient_list=[recruiter.email],
                from_email_override=from_email,
            )
    except Exception as e:
        logger.error(f"Failed to send interview approval result email: {e}")

@run_in_thread
def simulate_client_interview_details_email(schedule_id, action_user_id=None):
    try:
        schedule = InterviewSchedule.objects.select_related('application__candidate', 'application__job', 'organization').get(id=schedule_id)
        client = schedule.application.job.client
        if client and client.email:
            from accounts.email_utils import send_org_email

            from_email = None
            if action_user_id:
                from accounts.models import User
                action_user = User.objects.filter(id=action_user_id).first()
                if action_user:
                    from_email = action_user.email

            context = {
                'client_name': client.company_name,
                'candidate_name': schedule.application.candidate.candidate_name,
                'interview_date': str(schedule.date),
                'interview_time': str(schedule.time),
                'mode': schedule.mode,
                'plain_message': f"An interview has been finalized for {schedule.application.candidate.candidate_name} on {schedule.date} at {schedule.time}."
            }
            send_org_email(
                organization=schedule.organization,
                subject=f"Interview Details: {schedule.application.candidate.candidate_name}",
                template_name='generic_email',
                context=context,
                recipient_list=[client.email],
                from_email_override=from_email,
            )
    except Exception as e:
        logger.error(f"Failed to send client interview details email: {e}")

@run_in_thread
def send_attendance_update_email(schedule_id, action_user_id=None):
    try:
        schedule = InterviewSchedule.objects.select_related('application__candidate', 'application__job', 'organization').get(id=schedule_id)
        manager = schedule.application.job.hiring_manager or schedule.application.job.created_by
        if manager and manager.email:
            from accounts.email_utils import send_org_email

            from_email = None
            if action_user_id:
                from accounts.models import User
                action_user = User.objects.filter(id=action_user_id).first()
                if action_user:
                    from_email = action_user.email

            context = {
                'manager_name': manager.name,
                'candidate_name': schedule.application.candidate.candidate_name,
                'attendance_status': schedule.attendance_status,
                'plain_message': f"The attendance status for {schedule.application.candidate.candidate_name}'s interview has been updated to {schedule.attendance_status}."
            }
            send_org_email(
                organization=schedule.organization,
                subject=f"Interview Attendance Update: {schedule.application.candidate.candidate_name}",
                template_name='generic_email',
                context=context,
                recipient_list=[manager.email],
                from_email_override=from_email,
            )
    except Exception as e:
        logger.error(f"Failed to send attendance update email: {e}")

