# -*- coding: utf-8 -*-
# Copyright (c) 2021, omar jaber and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from datetime import date
from frappe.utils import today, add_days, get_url
from frappe.utils import get_datetime, add_to_date, getdate, get_link_to_form, now_datetime, nowdate, cstr

class PACI(Document):
	def validate(self):
		self.set_grd_values()

	def set_grd_values(self):
		if not self.grd_supervisor:
			self.grd_supervisor = frappe.db.get_value('GRD Settings', None, 'default_grd_supervisor')
		if not self.grd_operator:
			self.grd_operator = frappe.db.get_value('GRD Settings', None, 'default_grd_operator')
	
	def on_submit(self):
		self.validate_mandatory_fields_on_submit()
		self.set_New_civil_id_Expiry_date_in_employee_doctype()
		self.db_set('completed',"Yes")
		self.db_set('completed_on', today())
	
	def validate_mandatory_fields_on_submit(self):
		if self.apply_civil_id_online == "No":
			frappe.throw(_("GRD Operator Must Apply Civil ID online to Submit"))
		if not self.upload_civil_id_payment:
			frappe.throw(_("GRD Operator Must Upload Paymnent Invoice to Submit"))
		if not self.upload_civil_id:
			frappe.throw(_("GRD Operator Must Upload Civil ID to Submit"))
		if not self.new_civil_id_expiry_date:
			frappe.throw(_("GRD Operator Must The New Civil ID to Submit"))

	def set_New_civil_id_Expiry_date_in_employee_doctype(self):
		today = date.today()
		employee = frappe.get_doc('Employee', self.employee)
		employee.civil_id_expiry_date = self.new_civil_id_expiry_date # update the date of expiry

		employee.append("one_fm_employee_documents", {
		"attach": self.upload_civil_id,
		"document_name": "Civil ID Expiry Attachment",
		"issued_on":today,
		"valid_till":self.new_civil_id_expiry_date
		})
		employee.save()

# Create PACI record once a month for renewals list  
def create_PACI_renewal(preparation_name):

    employee_in_preparation = frappe.get_doc('Preparation',preparation_name)
    if employee_in_preparation.preparation_record:
        for employee in employee_in_preparation.preparation_record:
            if employee.renewal_or_extend == 'Renewal' and employee.nationality != 'Kuwaiti':
                create_PACI(frappe.get_doc('Employee',employee.employee),preparation_name)



def create_PACI(employee,preparation_name):
        # Create New Work Permit: 1. New Overseas, 2. New Kuwaiti, 3. Work Transfer
        PACI_new = frappe.new_doc('PACI')
        PACI_new.employee = employee.name
        PACI_new.preparation = preparation_name
        PACI_new.save()

#At 4pm Notify GRD Operator
def system_checks_grd_operator_apply_online():
	filter1 = {'apply_civil_id_online':['!=','Yes']}
	employee_list = frappe.db.get_list('PACI',filter, ['name','grd_operator','grd_supervisor'])
	if len(employee_list) > 0:
		paci_notify_first_grd_operator()

# Notify GRD Operator at 11:30 am 
def paci_notify_first_grd_operator():
    paci_notify_grd_operator('yellow')

# Notify GRD Operator at 12:00 am 
def paci_notify_again_grd_operator():
    paci_notify_grd_operator('red')

#At 4pm Notify GRD Operator
def system_checks_grd_operator_upload_and_update_civil_Id():
	filter2 = {'upload_civil_id':['=',' '],'new_civil_id_expiry_date':['=',' ']}
	employee_list = frappe.db.get_list('PACI',filter, ['name','grd_operator','grd_supervisor'])
	if len(employee_list) > 0:
		paci_notify_first_grd_operator()

# Notify GRD Operator at 9:00 am 
def paci_notify_first_grd_operator():
    paci_notify_grd_operator('yellow')

# Notify GRD Operator at 9:30 am 
def paci_notify_again_grd_operator():
    paci_notify_grd_operator('red')

def paci_notify_grd_operator(reminder_indicator):
    # Get paci list
    today = date.today()
    filters = {'docstatus': 0,'reminded_grd_operator': 0, 'reminded_grd_operator_again':0}
    if reminder_indicator == 'red':
        filters['reminded_grd_operator'] = 1
        filters['reminded_grd_operator_again'] = 0
                                                            
    paci_list = frappe.db.get_list('PACI', filters, ['name', 'grd_operator', 'grd_supervisor'])
    # send grd supervisor if reminder for second time (red)
    cc = [paci_list[0].grd_supervisor] if reminder_indicator == 'red' else []
    email_notification_to_grd_user('grd_operator', paci_list, reminder_indicator, 'Submit', cc)

def email_notification_to_grd_user(grd_user, paci_list, reminder_indicator, action, cc=[]):
    recipients = {}

    for paci in paci_list:
        page_link = get_url("http://192.168.8.102/desk#Form/PACI/"+paci.name)
        message = "<a href='{0}'>{1}</a>".format(page_link, paci.name)
        if paci[grd_user] in recipients:
            recipients[paci[grd_user]].append(message)#add the message in the empty list
        else:
            recipients[paci[grd_user]]=[message]

    if recipients:
        for recipient in recipients:
            subject = 'PACI {0}'.format(paci.name)#added
            message = "<p>Please {0} PACI listed below</p><ol>".format(action)
            for msg in recipients[recipient]:
                message += "<li>"+msg+"</li>"
            message += "<ol>"
            frappe.sendmail(
                recipients=[recipient],
                cc=cc,
                subject=_('{0} PACI'.format(action)),
                message=message,
                header=['PACI Reminder', reminder_indicator],
            )
            to_do_to_grd_users(_('{0} PACI'.format(action)), message, recipient)
            create_notification_log(subject, message, [paci.grd_user], paci)#added

def to_do_to_grd_users(subject, description, user):
    frappe.get_doc({
        "doctype": "ToDo",
        "subject": subject,
        "description": description,
        "owner": user,
        "date": today()
    }).insert(ignore_permissions=True)

def create_notification_log(subject, message, for_users, reference_doc):
    for user in for_users:
        doc = frappe.new_doc('Notification Log')
        doc.subject = subject
        doc.email_content = message
        doc.for_user = user
        doc.document_type = reference_doc.doctype
        doc.document_name = reference_doc.name
        doc.from_user = reference_doc.modified_by
        #doc.insert(ignore_permissions=True)


# Set dates automatically once each field been set by the grd operator
@frappe.whitelist()
def set_dates():
    currentDateTime = now_datetime()
    return currentDateTime