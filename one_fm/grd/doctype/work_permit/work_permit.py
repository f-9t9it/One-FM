# -*- coding: utf-8 -*-
# Copyright (c) 2020, omar jaber and contributors
# For license information, please see license.txt
from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import today, add_days, get_url
from frappe import _
from frappe.permissions import has_permission
from frappe.utils.user import get_users_with_role
from datetime import date, timedelta
import calendar
from datetime import date
from dateutil.relativedelta import relativedelta
from frappe.utils import get_datetime, add_to_date, getdate, get_link_to_form, now_datetime, nowdate, cstr

class WorkPermit(Document):
    
    def validate(self):
        #pass
        self.set_grd_values()
        

    def set_grd_values(self):
        if not self.grd_supervisor:
            self.grd_supervisor = frappe.db.get_single_value("GRD Settings", "default_grd_supervisor")
        if not self.grd_operator:
            self.grd_supervisor = frappe.db.get_single_value("GRD Settings", "default_grd_operator")#frappe.db.get_value('GRD Settings', None, 'default_grd_operator')
    
    def on_submit(self):
        #self.validate_mandatory_fields_on_submit()# GRD Operator # Notify # GRD Supervisor
        self.check_wp_status()
        if self.work_permit_approved == "Yes" and self.upload_work_permit and self.attach_invoice and self.new_work_permit_expiry_date:
            self.db_set('work_permit_status', 'Approved')
            self.clean_old_wp_record_in_employee_doctype()
            self.set_work_permit_attachment_in_employee_doctype()
        elif self.work_permit_approved == "No" and not self.upload_work_permit and not self.attach_invoice and not self.new_work_permit_expiry_date and frappe.session.user == self.grd_operator:
            frappe.throw(_("Upload The Required Documents To Submit"))
        elif frappe.session.user == self.grd_supervisor and self.grd_supervisor_check_and_approval_wp_online == 'Yes':
            frappe.throw(_("Thaks For Saving. Operator Needs To Upload The Required Documents To Submit"))
        else:
            frappe.throw(_("Upload The Required Documents To Submit"))

        

    def check_wp_status(self):
        users1 = get_users_with_role('GRD Operator')
        users2 = get_users_with_role('GRD Supervisor')
        if self.work_permit_status == "Pending" and frappe.session.user == self.grd_operator and self.grd_supervisor_check_and_approval_wp_online == 'No':
            frappe.throw(_("{0} ({1}) need to be accepted by GRD supervisor. Please wait.").format(_(self.doctype), self.name))
            self.notify_grd_supervisor()
        if self.work_permit_status == "Accepted" and frappe.session.user == self.grd_supervisor and self.grd_supervisor_check_and_approval_wp_online == "Yes":
            self.notify_grd_operator()
            self.validate_mandatory_fields_for_grd_operator_again()

    def validate_mandatory_fields_for_grd_operator_again(self):
        users = get_users_with_role('GRD Operator')
        filtered_users = []
        for user in users:
            if has_permission(doctype=self.doctype, user=user):
                filtered_users.append(user)
            if filtered_users and len(filtered_users) > 0:
                if self.work_permit_status == "Accepted" and self.grd_supervisor_check_and_approval_wp_online == 'Yes' and frappe.session.user == self.grd_operator:
                    if self.work_permit_approved == "No" and not self.upload_work_permit and not self.attach_invoice:
                        frappe.throw(_("Upload Required Documents To Submit"))


    def notify_grd_supervisor(self):
        print("something")
        users = get_users_with_role('GRD Supervisor')
        filtered_users = []
        for user in users:
            if has_permission(doctype=self.doctype, user=user):
                filtered_users.append(user)
            if filtered_users and len(filtered_users) > 0:
                if self.grd_operator_apply_work_permit_on_ashal == "Yes" and self.work_permit_status == "Pending" and frappe.session.user == self.grd_supervisor:
                    page_link = get_url("/desk#Form/Work Permit/" + self.name)
                    message = "<p>Please Review and Accept WP Online<a href='{0}'>{1}</a> Applied by {2}.</p>".format(page_link, self.name, self.grd_operator)
                    subject = 'Apply WP Online by {0}'.format(self.grd_operator)
                    send_email(self, [self.grd_supervisor], message, subject)
                    create_notification_log(subject, message, [self.grd_supervisor], self)             
        self.save()
        self.reload()

    def notify_grd_operator(self):
        if self.grd_supervisor_check_and_approval_wp_online == "Yes" and self.work_permit_status == "Accepted" and frappe.session.user == self.grd_operator:
            page_link = get_url("/desk#Form/Work Permit/" + self.name)
            message = "<p>Please Submit WP<a href='{0}'>{1}</a> Accepted by {2}.</p>".format(page_link, self.name, self.grd_supervisor)
            subject = 'Check WP Online by {0}'.format(self.grd_supervisor)
            send_email(self, [self.grd_operator], message, subject)
            create_notification_log(subject, message, [self.grd_operator], self)
    
    def clean_old_wp_record_in_employee_doctype(self):
        """ Clean old wp records in employee """
        to_remove = []
        employee = frappe.get_doc('Employee', self.employee)
        if employee.one_fm_employee_documents:
            for document in employee.one_fm_employee_documents:
                print(document.document_name)
                if document.document_name == "Work Permit Attachment":
                    to_remove.append(document)
            [document.delete(document) for document in to_remove]

    def set_work_permit_attachment_in_employee_doctype(self):
        today = date.today()
        employee = frappe.get_doc('Employee', self.employee)
        filters= {"document_name":['=',"Work Permit Attachment"]}
        employee_wp_document = frappe.db.get_list('Employee Document',filters, ['document_name','attach','issued_on','valid_till'])
        employee.append("one_fm_employee_documents", {
            "attach": self.upload_work_permit,
            "document_name": "Work Permit Attachment",
            "issued_on":today,
            "valid_till":self.new_work_permit_expiry_date
        })
        employee.work_permit = self.name # add the latest work permit link
        employee.work_permit_expiry_date = self.new_work_permit_expiry_date # add the latest work permit link
        employee.save()
        
    def get_required_documents(self):
        set_required_documents(self)

def set_required_documents(doc):
    if frappe.db.exists('Work Permit Required Documents Template', {'work_permit_type':doc.work_permit_type}):
        #getting the required documents template based on the wp type
        document_list_template = frappe.get_doc('Work Permit Required Documents Template', {'work_permit_type':doc.work_permit_type})
        employee = frappe.get_doc('Employee', doc.employee)#getting employee info.
        if document_list_template and document_list_template.work_permit_document:####### Don't get 
            for wpd in document_list_template.work_permit_document:
                documents_required = doc.append('documents_required')#in work permit doctype points to Work Permit Required Documents
                documents_required.required_document = wpd.required_document
                if employee.one_fm_employee_documents:# from employee dt
                    for ed in employee.one_fm_employee_documents:
                        if wpd.required_document == ed.document_name and ed.attach:#check if both documents are equal
                            documents_required.attach = ed.attach#add the attach document from (Employee Document)dt to (Work permit Required Document) attch field
            frappe.db.commit()


# will craete a list of work permit based on employee renewals
@frappe.whitelist()
def get_employee_data_for_work_permit(employee_name):
    work_permit_exist = frappe.db.exists('Work Permit', {'employee': employee_name, 'docstatus': 1})
    return work_permit_exist

# Create Work Permit record once a month for renewals list  
def create_work_permit_renewal(preparation_name):
#Get employees of the choosen preparation record
    employee_in_preparation = frappe.get_doc('Preparation',preparation_name)
    if employee_in_preparation.preparation_record:
        for employee in employee_in_preparation.preparation_record:
            if employee.renewal_or_extend == 'Renewal':
                create_work_permit(frappe.get_doc('Employee',employee.employee),preparation_name)
      
def create_work_permit(employee,preparation_name):
    #Set the date of application to be before 14 days of residency expriy date
    start_day = add_days(employee.residency_expiry_date, -14)
    # setting type of renewal work permit
    if employee.one_fm_nationality == "Kuwaiti":
        work_permit_type_renewal = "Renewal Kuwaiti"
    if employee.one_fm_nationality != "Kuwaiti":
        work_permit_type_renewal = "Renewal Non Kuwaiti"
  
    if employee.one_fm_work_permit:
        # Renew Work Permit: 1. Renew Kuwaiti Work Permit, 2. Renew Overseas Work Permit
        work_permit = frappe.get_doc('Work Permit', employee.one_fm_work_permit)
        new_work_permit = frappe.copy_doc(work_permit)
        new_work_permit.preparation = preparation_name
        new_work_permit.work_permit_type = work_permit_type_renewal
        new_work_permit.date_of_application = start_day
        new_work_permit.insert()
        
        
    else:
        # Create New Work Permit: 1. New Overseas, 2. New Kuwaiti, 3. Work Transfer
        work_permit = frappe.new_doc('Work Permit')
        work_permit.employee = employee.name
        work_permit.preparation = preparation_name
        work_permit.work_permit_type = work_permit_type_renewal
        work_permit.date_of_application = start_day
        work_permit.save()

#System check at 4pm if grd operator submit the application online (cron)
def system_checks_grd_operator_submit_application_online():
    """ Notify GRD Operator to apply for wp  System checks at 4pm """
    today = date.today()
    filters = {
        'docstatus': 0,# dt is draft 
        #'date_of_application': ['=',today],
        'grd_operator_apply_work_permit_on_ashal': ['=','No'],
        'grd_supervisor_check_and_approval_wp_online': ['=','No']
    }
    work_permit_list = frappe.db.get_list('Work Permit', filters, ['name', 'grd_operator'])
    if len(work_permit_list) > 0:
       #print(work_permit_list)
       work_permit_notify_first_grd_operator() # 9am
   

#System check at 4pm if grd supervisor accept the application online (cron)
def system_checks_grd_operator_complete_application():
    """ Notify GRD Operator to complete wp System checks at 4pm """
    today = date.today()
    filters = {
    'docstatus': 0, 
    'grd_operator_apply_work_permit_on_ashal': ['=','Yes'],
    'grd_supervisor_check_and_approval_wp_online': ['=','Yes'], #grd_supervisor_check_and_approval_wp_online. work_permit_approved
    'work_permit_approved': ['=','No']# grd operator task

    }
    work_permit_list = frappe.db.get_list('Work Permit', filters, ['name', 'grd_operator'])
    if len(work_permit_list) > 0:
        work_permit_notify_grd_operator_check_approval() # 9am work_permit_notify_grd_supervisor_check_approval

# Notify GRD Operator at 9:00 am (cron)
def work_permit_notify_first_grd_operator():#will notify the grd operator every 8:30 am to fill the work permit for the list of employee
    work_permit_notify_grd_operator('yellow')

# Notify GRD Operator at 9:30 am (cron)
def work_permit_notify_again_grd_operator():
    work_permit_notify_grd_operator('red')

# Notify GRD Supervisor at 4:00 pm to approve and check online submit (cron)
def work_permit_notify_grd_supervisor_to_approve():
    work_permit_notify_grd_supervisor('yellow')


# Notify GRD Operator at 9 am (check approval of wp) (cron)
def work_permit_notify_grd_operator_check_approval(): #work_permit_notify_grd_supervisor_check_approval
    work_permit_notify_grd_operator_to_check_and_complete('yellow') 

# Notify Finance Dept. 4:00 pm - Work Permit is Approved by the Govt. and do Payments
# def work_permit_notify_finance_dept_for_payment():
#     # Get work permit list
#     filters = {
#         'docstatus': 1, 'work_permit_approved': 'Yes', 'work_permit_status': 'Approved',
#         'payment_transferred_from_finance_dept': 0, 'upload_work_permit': ['!=',''],
#         'attach_invoice':['!=','']
#     }
#     work_permit_list = frappe.db.get_list('Work Permit', filters, ['name', 'notify_finance_user'])
#     email_notification_to_grd_user('notify_finance_user', work_permit_list, reminder_indicator, 'Take action on Payment Transfer Requested for ')

def work_permit_notify_grd_operator_to_check_and_complete(reminder_indicator):
    """ Notify GRD Operator to complete wp System checks at 4pm """
    # Get work permit list
    filters = {'work_permit_approved': 'No','work_permit_status': 'Accepted'}
    work_permit_list = frappe.db.get_list('Work Permit', filters, ['name', 'grd_operator'])
    email_notification_to_grd_user('grd_operator', work_permit_list, reminder_indicator, 'Check Approval status of WP and Complete')


def work_permit_notify_grd_operator(reminder_indicator):
    """ Notify GRD Operator first and second time to remind applying online for WP """
    # Get work permit list
    today = date.today()
    filters = {'docstatus': 0,
    'grd_operator_apply_work_permit_on_ashal':['=','No'] ,'reminded_grd_operator': 0, 'reminded_grd_operator_again':0,'date_of_application': ['=',today]}
    if reminder_indicator == 'red':
        filters['reminded_grd_operator'] = 1
        filters['reminded_grd_operator_again'] = 0
                                                            
    work_permit_list = frappe.db.get_list('Work Permit', filters, ['name', 'grd_operator', 'grd_supervisor'])
    # send grd supervisor if reminder for second time (red)
    cc = [work_permit_list[0].grd_supervisor] if reminder_indicator == 'red' else []
    email_notification_to_grd_user('grd_operator', work_permit_list, reminder_indicator, 'Submit', cc)

    # Update reminded grd operator to 1
    if reminder_indicator == 'red':
        field = 'reminded_grd_operator_again'
    elif reminder_indicator == 'yellow':
        field = 'reminded_grd_operator'

    frappe.db.set_value("Work Permit", filters, field, 1)

def work_permit_notify_grd_supervisor(reminder_indicator): # at 9am checks grd supervisor approval on online application
    """ Notify GRD Supervisor to remind accepting WP on ASHAL application """
    # Get work permit list
    if reminder_indicator == 'yellow':
        filters = {'docstatus': 1, 
        'grd_operator_apply_work_permit_on_ashal':['=','Yes'],
        'grd_supervisor_check_and_approval_wp_online':['=','No']}

    work_permit_list = frappe.db.get_list('Work Permit', filters, ['name', 'grd_supervisor'])
    email_notification_to_grd_user('grd_supervisor', work_permit_list, reminder_indicator, 'Check and Accept')

def email_notification_to_grd_user(grd_user, work_permit_list, reminder_indicator, action, cc=[]):
    recipients = {}

    for work_permit in work_permit_list:
        page_link = get_url("http://192.168.8.102/desk#Form/Work Permit/"+work_permit.name)
        message = "<a href='{0}'>{1}</a>".format(page_link, work_permit.name)
        if work_permit[grd_user] in recipients:
            recipients[work_permit[grd_user]].append(message)#add the message in the empty list
        else:
            recipients[work_permit[grd_user]]=[message]

    if recipients:
        for recipient in recipients:
            subject = 'Work Permit {0}'.format(work_permit.name)#added
            message = "<p>Please {0} Work Permit listed below</p><ol>".format(action)
            for msg in recipients[recipient]:
                message += "<li>"+msg+"</li>"
            message += "<ol>"
            frappe.sendmail(
                recipients=[recipient],
                cc=cc,
                subject=_('{0} Work Permit'.format(action)),
                message=message,
                header=['Work Permit Reminder', reminder_indicator],
            )
            to_do_to_grd_users(_('{0} Work Permit'.format(action)), message, recipient)
            create_notification_log(subject, message, [work_permit.grd_user], work_permit)#added

def to_do_to_grd_users(subject, description, user):
    frappe.get_doc({
        "doctype": "ToDo",
        "subject": subject,
        "description": description,
        "owner": user,
        "date": today()
    }).insert(ignore_permissions=True)

def send_email(doc, recipients, message, subject):
	frappe.sendmail(
		recipients= recipients,
		subject=subject,
		message=message,
		reference_doctype=doc.doctype,
		reference_name=doc.name
	)
def create_notification_log(subject, message, for_users, reference_doc):
    for user in for_users:
        doc = frappe.new_doc('Notification Log')
        doc.subject = subject
        doc.email_content = message
        doc.for_user = user
        doc.document_type = reference_doc.doctype
        doc.document_name = reference_doc.name
        doc.from_user = reference_doc.modified_by
        doc.save(ignore_permissions=True)
		