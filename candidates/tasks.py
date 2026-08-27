import logging
import threading
from notifications.models import Notification
from candidates.models import InterviewSchedule, Candidate, Application
from accounts.models import User, UserRole
from django.conf import settings

logger = logging.getLogger(__name__)

def shorten_location(location):
    """Extracts city from a long location string/address by picking the first non-digit part."""
    if not location or not isinstance(location, str):
        return ""
    parts = [p.strip() for p in location.split(',') if p.strip()]
    if not parts:
        return location
    for part in parts:
        if not any(c.isdigit() for c in part) and len(part) > 2:
            return part
    return parts[0]

def run_in_thread(func):
    def wrapper(*args, **kwargs):
        thread = threading.Thread(target=func, args=args, kwargs=kwargs)
        thread.start()
        return thread
    return wrapper

@run_in_thread
def simulate_client_submission_email(application_id, client_email, recipient_name=None, header_color=None, text_color=None):
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
            'plain_message': f"Please find the profile of {candidate.candidate_name} for the position of {application.job.title}.\nKindly review the profile and share your feedback or next steps.",
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
                    
                    if col_norm in ['candidate_name', 'name', 'candidate']: val = candidate.candidate_name
                    elif col_norm in ['email', 'candidate_email_id', 'candidate_email', 'email_id']: val = candidate.email
                    elif col_norm in ['phone', 'contact', 'contacts', 'mobile_no.', 'mobile_no', 'mobile_number', 'mobile']: val = candidate.contact
                    elif col_norm in ['total_experience', 'experience', 'total_exp', 'exp']: val = candidate.experience
                    elif col_norm in ['current_company', 'company', 'organization']: val = candidate.current_company
                    elif col_norm in ['current_designation', 'current_profile', 'designation', 'role', 'c._designation', 'c_designation']: val = candidate.current_profile
                    elif col_norm in ['current_ctc', 'ctc', 'cctc']: 
                        c_val = application.current_ctc or candidate.current_ctc
                        val = f"₹{c_val}" if c_val else ""
                    elif col_norm in ['expected_ctc', 'expected_ctc', 'ectc']: 
                        e_val = application.expected_ctc or candidate.expected_ctc
                        val = f"₹{e_val}" if e_val else ""
                    elif col_norm in ['notice_period', 'notice']: val = application.notice_period or candidate.notice_period
                    elif col_norm in ['current_location', 'address', 'location']: val = shorten_location(candidate.current_location)
                    elif col_norm == 'preferred_location': val = shorten_location(candidate.preferred_location)
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
                {'label': 'Contact', 'value': candidate.contact},
                {'label': 'Email', 'value': candidate.email},
                {'label': 'Current Role', 'value': candidate.current_profile},
                {'label': 'Experience', 'value': candidate.experience},
                {'label': 'Location', 'value': shorten_location(candidate.current_location)},
            ]
            c_ctc = application.current_ctc or candidate.current_ctc
            e_ctc = application.expected_ctc or candidate.expected_ctc
            np = application.notice_period or candidate.notice_period
            
            if c_ctc: tracker_fields.append({'label': 'Current CTC', 'value': f"₹{c_ctc}"})
            if e_ctc: tracker_fields.append({'label': 'Expected CTC', 'value': f"₹{e_ctc}"})
            if np: tracker_fields.append({'label': 'Notice Period', 'value': np})

        context['tracker_fields'] = tracker_fields
        context['header_color'] = header_color
        context['text_color'] = text_color
        
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

        # Determine who sent it to set as the "From" address
        from_email = None
        if hasattr(application, 'client_submission') and application.client_submission.sent_by:
            from_email = application.client_submission.sent_by.email
        elif application.job.hiring_manager:
            from_email = application.job.hiring_manager.email
            
        context['plain_message'] = f"PFA resume for {application.job.title} – {application.job.location}."

        send_org_email(
            organization=org,
            subject=f"Resume for {application.job.title} – {application.job.location}.",
            template_name='client_submission',
            context=context,
            recipient_list=[client_email],
            attachments=attachments,
            from_email_override=from_email
        )
        logger.info(f"Client submission email sent for application {application_id} to {client_email}")
    except Exception as e:
        logger.error(f"Client submission email failed for application {application_id}: {e}")


@run_in_thread
def simulate_bulk_client_submission_email(application_ids, client_email, recipient_name=None, header_color=None, text_color=None, cc_emails=None):
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
            'plain_message': f"PFA resumes for {job.title} – {job.location}.",
        }

        tracker_headers, candidates_data, attachments, synopses = _build_tracker_and_attachments_for_apps(applications, job)

        context['tracker_headers'] = tracker_headers
        context['candidates_data'] = candidates_data
        context['synopses'] = synopses
        context['header_color'] = header_color
        context['text_color'] = text_color

        from_email = None
        if hasattr(first_app, 'client_submission') and first_app.client_submission.sent_by:
            from_email = first_app.client_submission.sent_by.email
        elif first_app.job.hiring_manager:
            from_email = first_app.job.hiring_manager.email

        send_org_email(
            organization=org,
            subject=f"Resumes for {job.title} – {job.location}.",
            template_name='bulk_client_submission',
            context=context,
            recipient_list=[client_email],
            attachments=attachments,
            from_email_override=from_email,
            cc_list=cc_emails
        )
        logger.info(f"Bulk client submission email sent for {len(applications)} apps to {client_email}")
    except Exception as e:
        logger.error(f"Bulk client submission email failed: {e}")


@run_in_thread
def simulate_interview_reminder(interview_schedule_id, action_user_id=None):
    """Send interview reminder notification (in-app) + email via org SMTP."""
    try:
        schedule = InterviewSchedule.objects.select_related(
            'application__candidate', 'application__job', 'organization'
        ).get(id=interview_schedule_id)
        application = schedule.application
        candidate = application.candidate
        org = application.organization

        from_email_override = None
        if action_user_id:
            try:
                from accounts.models import User
                action_user = User.objects.get(id=action_user_id)
                from_email_override = action_user.email
            except Exception as e:
                logger.warning(f"Could not get action_user {action_user_id} for interview reminder email override: {e}")

        # In-app notifications for the uploader (ensure same organization)
        uploader = application.created_by or candidate.uploaded_by
        if uploader and uploader.organization_id == org.id:
            from notifications.services import NotificationService
            NotificationService.create_notification(
                user=uploader,
                organization=org,
                title="Interview Reminder",
                message=f"Upcoming interview for {schedule.application.candidate.candidate_name} scheduled at {schedule.time.strftime('%I:%M %p') if schedule.time else ''}.",
                type='warning',
                link=f"/positions/{application.job.id}/pipeline",
                name=schedule.application.candidate.candidate_name,
                event="Interview Reminder",
                process="Interview"
            )

            # Also send email reminder
            try:
                from accounts.email_utils import send_org_email
                frontend_base = getattr(settings, 'FRONTEND_URL', getattr(settings, 'FRONTEND_BASE_URL', 'https://recruitos.jmstech.co'))
                context = {
                    'recruiter_name': uploader.name,
                    'candidate_name': candidate.candidate_name,
                    'job_title': application.job.title,
                    'interview_date': str(schedule.date),
                    'interview_time': str(schedule.time),
                    'interview_mode': schedule.mode,
                    'interviewer_name': schedule.interviewer_name,
                    'notes': schedule.notes,
                    'candidate_link': f"{frontend_base}/positions/{application.job.id}/pipeline",
                    'plain_message': f"This is a reminder that the interview for {candidate.candidate_name} for {application.job.title} is scheduled for tomorrow.\nPlease review the interview details and ensure all necessary arrangements are in place.",
                    'notification_name': candidate.candidate_name,
                    'notification_event': "Interview Reminder",
                    'notification_process': "Interview"
                }
                send_org_email(
                    organization=org,
                    subject=f"Interview Reminder: {candidate.candidate_name} — {application.job.title}",
                    template_name='interview_reminder',
                    context=context,
                    recipient_list=[uploader.email],
                    from_email_override=from_email_override
                )
            except Exception as email_err:
                logger.warning(f"Interview reminder email failed for {uploader.email}: {email_err}")

        logger.info(f"Interview reminder processed for schedule {interview_schedule_id}")
    except InterviewSchedule.DoesNotExist:
        logger.warning(f"InterviewSchedule {interview_schedule_id} not found")
    except Exception as e:
        logger.error(f"Interview reminder error: {e}")


@run_in_thread
def simulate_resume_submission_notification(obj_id):
    """Notify about new resume submission. Supports Application (job-specific) or pure pool Candidate (obj_id = candidate.id)."""
    try:
        application = Application.objects.select_related('candidate', 'job', 'job__client', 'organization').get(id=obj_id)
        candidate = application.candidate
        org = application.organization
        
        manager = application.job.hiring_manager or application.job.created_by
        
        frontend_base = getattr(settings, 'FRONTEND_URL', getattr(settings, 'FRONTEND_BASE_URL', 'https://recruitos.jmstech.co'))
        
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
            'synopsis': application.synopsis if application.synopsis else None,
            'url': f"{frontend_base}/approvals/{application.job.id}",
            'plain_message': f"A new candidate, {candidate.candidate_name}, has been added for {application.job.title}.\nPlease review the candidate profile and take the necessary action.",
            'notification_name': candidate.candidate_name,
            'notification_event': "New Resume",
            'notification_process': "Application"
        }
        
        from accounts.email_utils import send_org_email
        
        # Notify the uploader (ensure same organization)
        uploader = application.created_by or application.candidate.uploaded_by
        if uploader and uploader.organization_id == org.id:
            from notifications.services import NotificationService
            NotificationService.create_notification(
                user=uploader,
                organization=org,
                title="New Resume Submitted",
                message=f"{candidate.candidate_name} submitted a resume for '{application.job.title}'.",
                type='info',
                link=f"/approvals/{application.job.id}",
                name=candidate.candidate_name,
                event="New Resume",
                process="Application"
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
        
        frontend_base = getattr(settings, 'FRONTEND_URL', getattr(settings, 'FRONTEND_BASE_URL', 'https://recruitos.jmstech.co'))
        
        context = {
            'candidate_name': candidate.candidate_name,
            'candidate_email': candidate.email,
            'contact': candidate.contact,
            'current_profile': candidate.current_profile or 'N/A',
            'current_company': candidate.current_company or 'N/A',
            'current_location': candidate.current_location or 'N/A',
            'education': ', '.join([e.get('degree', '') if isinstance(e, dict) else str(e) for e in candidate.education]) if candidate.education and isinstance(candidate.education, list) else 'N/A',
            'skills': ', '.join(candidate.skills) if candidate.skills else 'N/A',
            'url': f"{frontend_base}/candidates/{candidate.id}",
            'plain_message': f"A new candidate, {candidate.candidate_name}, has been added.",
            'notification_name': candidate.candidate_name,
            'notification_event': "New Resume",
            'notification_process': "Talent Pool"
        }
        
        if candidate.uploaded_by:
            from notifications.services import NotificationService
            NotificationService.create_notification(
                user=candidate.uploaded_by,
                organization=org,
                title="New Resume in Pool",
                message=f"{candidate.candidate_name} added to talent pool.",
                type='info',
                link=f"/candidates/{candidate.id}",
                name=candidate.candidate_name,
                event="New Resume",
                process="Talent Pool"
            )
                
        logger.info(f"Resume submission notification fired for pool candidate {obj_id}")
    except Candidate.DoesNotExist:
        logger.warning(f"No Application or Candidate found for id={obj_id}")
    except Exception as e:
        logger.error(f"Pool notification error: {e}")

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

            frontend_base = getattr(settings, 'FRONTEND_URL', getattr(settings, 'FRONTEND_BASE_URL', 'https://recruitos.jmstech.co'))
            
            context = {
                'manager_name': manager.name,
                'candidate_name': schedule.application.candidate.candidate_name,
                'job_title': schedule.application.job.title,
                'interview_date': str(schedule.date),
                'interview_time': str(schedule.time),
                'url': f"{frontend_base}/positions/{schedule.application.job.id}/pipeline",
                'plain_message': f"An interview has been proposed for {schedule.application.candidate.candidate_name} and requires your approval.",
                'notification_name': schedule.application.candidate.candidate_name,
                'notification_event': "Approval Required",
                'notification_process': "Interview"
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

            frontend_base = getattr(settings, 'FRONTEND_URL', getattr(settings, 'FRONTEND_BASE_URL', 'https://recruitos.jmstech.co'))
            
            context = {
                'recruiter_name': recruiter.name,
                'candidate_name': schedule.application.candidate.candidate_name,
                'status': schedule.manager_approval_status,
                'url': f"{frontend_base}/positions/{schedule.application.job.id}/pipeline",
                'plain_message': f"The interview schedule for {schedule.application.candidate.candidate_name} has been {schedule.manager_approval_status}.",
                'notification_name': schedule.application.candidate.candidate_name,
                'notification_event': f"Approval {schedule.manager_approval_status.title()}",
                'notification_process': "Interview"
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

def _build_tracker_and_attachments_for_apps(applications, job):
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
        columns_to_extract = ['candidate_name', 'contact', 'email', 'current_profile', 'experience', 'current_location', 'current_ctc', 'expected_ctc', 'notice_period']
        tracker_headers = ['Candidate Name', 'Contact', 'Email', 'Current Role', 'Experience', 'Location', 'Current CTC', 'Expected CTC', 'Notice Period']

    candidates_data = []
    attachments = []
    synopses = []

    for idx, app in enumerate(applications):
        candidate = app.candidate
        
        if app.synopsis:
            synopses.append({'name': candidate.candidate_name, 'text': app.synopsis})
            
        row = []
        for col in columns_to_extract:
            val = ""
            col_norm = col.strip().lower().replace(' ', '_')
            
            if col_norm in ['sr._no.', 'sr._no', 'sr_no.', 'sr_no', 'serial_no', 's._no.', 's_no', 's.no.', 's.no', 'sr']: val = idx + 1
            elif col_norm in ['candidate_name', 'name', 'candidate']: val = candidate.candidate_name
            elif col_norm in ['email', 'candidate_email_id', 'candidate_email', 'email_id']: val = candidate.email
            elif col_norm in ['phone', 'contact', 'contacts', 'mobile_no.', 'mobile_no', 'mobile_number', 'mobile']: val = candidate.contact
            elif col_norm in ['total_experience', 'experience', 'total_exp', 'exp']: val = candidate.experience
            elif col_norm in ['current_company', 'company', 'organization']: val = candidate.current_company
            elif col_norm in ['current_designation', 'current_profile', 'designation', 'role', 'c._designation', 'c_designation']: val = candidate.current_profile
            elif col_norm in ['current_ctc', 'ctc', 'cctc']: 
                c_val = app.current_ctc or candidate.current_ctc
                val = f"₹{c_val}" if c_val else ""
            elif col_norm in ['expected_ctc', 'ectc']: 
                e_val = app.expected_ctc or candidate.expected_ctc
                val = f"₹{e_val}" if e_val else ""
            elif col_norm in ['notice_period', 'notice']: val = app.notice_period or candidate.notice_period
            elif col_norm in ['current_location', 'address', 'location']: val = shorten_location(candidate.current_location)
            elif col_norm == 'preferred_location': val = shorten_location(candidate.preferred_location)
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
                
    return tracker_headers, candidates_data, attachments, synopses

@run_in_thread
def simulate_client_interview_details_email(schedule_id, action_user_id=None):
    try:
        schedule = InterviewSchedule.objects.select_related('application__candidate', 'application__job', 'organization').get(id=schedule_id)
        client = schedule.application.job.client
        if client and client.email:
            client_email = client.email
            recipient_name = client.company_name
            if schedule.application.job.team_member_id and isinstance(client.team_members, list):
                for tm in client.team_members:
                    if isinstance(tm, dict) and str(tm.get('id')) == str(schedule.application.job.team_member_id) and tm.get('email'):
                        client_email = tm.get('email')
                        recipient_name = tm.get('name', recipient_name)
                        break

            from accounts.email_utils import send_org_email

            manager = schedule.application.job.hiring_manager or schedule.application.job.created_by
            from_email = manager.email if manager and manager.email else None

            if not from_email and action_user_id:
                from accounts.models import User
                action_user = User.objects.filter(id=action_user_id).first()
                if action_user:
                    from_email = action_user.email

            tracker_headers, candidates_data, attachments, synopses = _build_tracker_and_attachments_for_apps(
                [schedule.application], schedule.application.job
            )

            context = {
                'recipient_name': recipient_name,
                'candidate_name': schedule.application.candidate.candidate_name,
                'interview_date': str(schedule.date),
                'interview_time': str(schedule.time),
                'mode': schedule.mode,
                'plain_message': f"{schedule.application.candidate.candidate_name} is available for {schedule.mode} on {schedule.date.strftime('%A')} ({schedule.date.strftime('%d-%m-%Y')}) at {schedule.time.strftime('%I:%M %p')}. Please confirm",
                'tracker_headers': tracker_headers,
                'candidates_data': candidates_data
            }
            send_org_email(
                organization=schedule.organization,
                subject=f"Interview Schedule for {schedule.application.job.title} – {schedule.application.job.location}.",
                template_name='generic_email',
                context=context,
                recipient_list=[client_email],
                from_email_override=from_email,
                attachments=attachments
            )
    except Exception as e:
        logger.error(f"Failed to send client interview details email: {e}")

@run_in_thread
def simulate_bulk_client_interview_details_email(schedule_ids, client_email, recipient_name, action_user_id=None):
    try:
        schedules = InterviewSchedule.objects.filter(id__in=schedule_ids).select_related('application__candidate', 'application__job', 'organization')
        if not schedules.exists():
            return
            
        organization = schedules.first().organization
        
        from accounts.email_utils import send_org_email

        manager = schedules.first().application.job.hiring_manager or schedules.first().application.job.created_by
        from_email = manager.email if manager and manager.email else None

        if not from_email and action_user_id:
            from accounts.models import User
            action_user = User.objects.filter(id=action_user_id).first()
            if action_user:
                from_email = action_user.email

        message_lines = []
        for schedule in schedules:
            message_lines.append(f"{schedule.application.candidate.candidate_name} is available for {schedule.mode} on {schedule.date.strftime('%A')} ({schedule.date.strftime('%d-%m-%Y')}) at {schedule.time.strftime('%I:%M %p')}. Please confirm")

        plain_message = "\n\n".join(message_lines)

        applications = [s.application for s in schedules]
        tracker_headers, candidates_data, attachments, synopses = _build_tracker_and_attachments_for_apps(
            applications, schedules.first().application.job
        )

        context = {
            'recipient_name': recipient_name,
            'plain_message': plain_message,
            'tracker_headers': tracker_headers,
            'candidates_data': candidates_data
        }
        send_org_email(
            organization=organization,
            subject=f"Interview Schedule for {schedules.first().application.job.title} – {schedules.first().application.job.location}.",
            template_name='generic_email',
            context=context,
            recipient_list=[client_email],
            from_email_override=from_email,
            attachments=attachments
        )
    except Exception as e:
        logger.error(f"Failed to send bulk client interview details email: {e}")

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
                'plain_message': f"The interview attendance for {schedule.application.candidate.candidate_name} has been recorded.\nPlease review the attendance status and proceed with the next step in the recruitment process."
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

@run_in_thread
def simulate_bulk_client_reminder_email(application_ids, client_email, recipient_name=None, header_color=None, text_color=None):
    """Send a bulk client reminder email containing a tracker of multiple candidates."""
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
        
        has_attended = False
        for app in applications:
            if hasattr(app, 'interview_schedule') and app.interview_schedule and app.interview_schedule.attendance_status == 'attended':
                has_attended = True
                break
            if app.status in ['interview-align', 'select', 'offered', 'joined']: # Add other post-interview statuses if needed
                has_attended = True
                break

        is_bulk = len(applications) > 1

        if has_attended:
            if is_bulk:
                plain_message = "Below mentioned candidates has appeared for the interview, request you to update Their status."
            else:
                plain_message = "Below mentioned candidate has appeared for the interview, request you to update His/her status."
        else:
            if is_bulk:
                plain_message = "Below mention resumes were shared earlier. Request you to update their status."
            else:
                plain_message = "Below mention resume was shared earlier. Request you to update his/her status."

        context = {
            'client_name': recipient_name,
            'job_title': job.title,
            'org_name': org.name,
            'sent_by': getattr(first_app, 'client_submission', None) and
                       getattr(first_app.client_submission.sent_by, 'name', 'RecruitOS') or 'RecruitOS',
            'plain_message': plain_message,
        }

        tracker_headers, candidates_data, attachments, synopses = _build_tracker_and_attachments_for_apps(applications, job)

        context['tracker_headers'] = tracker_headers
        context['candidates_data'] = candidates_data
        context['synopses'] = synopses
        context['header_color'] = header_color
        context['text_color'] = text_color

        from_email = None
        if hasattr(first_app, 'client_submission') and first_app.client_submission.sent_by:
            from_email = first_app.client_submission.sent_by.email
        elif first_app.job.hiring_manager:
            from_email = first_app.job.hiring_manager.email

        send_org_email(
            organization=org,
            subject=f"Status update for {job.title} – {job.location}.",
            template_name='bulk_client_submission',
            context=context,
            recipient_list=[client_email],
            attachments=attachments,
            from_email_override=from_email
        )
        logger.info(f"Bulk client reminder email sent for {len(applications)} apps to {client_email}")
    except Exception as e:
        logger.error(f"Bulk client reminder email failed: {e}")
