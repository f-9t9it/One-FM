# -*- coding: utf-8 -*-
# encoding: utf-8
from __future__ import unicode_literals
import frappe
from frappe import _
import frappe, os
import json
from frappe.model.document import Document
from frappe.utils import get_site_base_path
from erpnext.hr.doctype.employee.employee import get_holiday_list_for_employee
from frappe.utils.data import flt, nowdate, getdate, cint
from frappe.utils.csvutils import read_csv_content_from_uploaded_file, read_csv_content
from frappe.utils import cint, cstr, flt, nowdate, comma_and, date_diff, getdate, formatdate ,get_url, get_datetime
from datetime import tzinfo, timedelta, datetime
from dateutil import parser
from datetime import date
from erpnext.hr.doctype.leave_ledger_entry.leave_ledger_entry import expire_allocation, create_leave_ledger_entry
from dateutil.relativedelta import relativedelta
from frappe.utils import cint, cstr, date_diff, flt, formatdate, getdate, get_link_to_form, \
    comma_or, get_fullname, add_years, add_months, add_days, nowdate,get_first_day,get_last_day
import datetime

@frappe.whitelist(allow_guest=True)
def leave_appillication_on_submit(doc, method):
    if doc.status == "Approved":
        leave_appillication_paid_sick_leave(doc, method)
        update_employee_hajj_status(doc, method)

@frappe.whitelist(allow_guest=True)
def leave_appillication_on_cancel(doc, method):
    update_employee_hajj_status(doc, method)

@frappe.whitelist(allow_guest=True)
def leave_appillication_paid_sick_leave(doc, method):
    if doc.leave_type and frappe.db.get_value("Leave Type", doc.leave_type, 'one_fm_is_paid_sick_leave') == 1:
        create_additional_salary_for_paid_sick_leave(doc)

def create_additional_salary_for_paid_sick_leave(doc):
    salary = get_salary(doc.employee)
    daily_rate = salary/30
    from erpnext.hr.doctype.leave_application.leave_application import get_leave_details
    leave_details = get_leave_details(doc.employee, nowdate())
    curr_year_applied_days = 0
    if doc.leave_type in leave_details['leave_allocation'] and leave_details['leave_allocation'][doc.leave_type]:
        curr_year_applied_days = leave_details['leave_allocation'][doc.leave_type]['leaves_taken']
    if curr_year_applied_days == 0:
        curr_year_applied_days = doc.total_leave_days

    leave_payment_breakdown = get_leave_payment_breakdown(doc.leave_type)

    total_payment_days = 0
    if leave_payment_breakdown:
        threshold_days = 0
        for payment_breakdown in leave_payment_breakdown:
            payment_days = 0
            threshold_days += payment_breakdown.threshold_days
            if total_payment_days < doc.total_leave_days:
                if curr_year_applied_days >= threshold_days and (curr_year_applied_days - doc.total_leave_days) < threshold_days:
                    payment_days = threshold_days - (curr_year_applied_days-doc.total_leave_days) - total_payment_days
                elif curr_year_applied_days <= threshold_days: # Gives true this also doc.total_leave_days <= threshold_days:
                    payment_days = doc.total_leave_days - total_payment_days
                create_additional_salary(salary, daily_rate, payment_days, doc, payment_breakdown)
                total_payment_days += payment_days

    if total_payment_days < doc.total_leave_days and doc.total_leave_days-total_payment_days > 0:
        create_additional_salary(salary, daily_rate, doc.total_leave_days-total_payment_days, doc)

def create_additional_salary(salary, daily_rate, payment_days, leave_application, payment_breakdown=False):
    if payment_days > 0:
        deduction_percentage = 1
        salary_component = frappe.db.get_value("Leave Type", leave_application.leave_type, "one_fm_paid_sick_leave_deduction_salary_component")
        if payment_breakdown:
            deduction_percentage = payment_breakdown.salary_deduction_percentage/100
            salary_component = payment_breakdown.salary_component
        deduction_notes = """
            Employee Salary: <b>{0}</b><br>
            Daily Rate: <b>{1}</b><br>
            Deduction Days Number: <b>{2}</b><br>
            Deduction Percent: <b>{3}%</b>
        """.format(salary, daily_rate, payment_days, deduction_percentage*100)

        additional_salary = frappe.get_doc({
            "doctype":"Additional Salary",
            "employee": leave_application.employee,
            "salary_component": salary_component,
            "payroll_date": leave_application.from_date,
            "leave_application": leave_application.name,
            "notes": deduction_notes,
            "amount": payment_days*daily_rate*deduction_percentage
        }).insert(ignore_permissions=True)
        additional_salary.submit()

def get_leave_payment_breakdown(leave_type):
    leave_type_doc = frappe.get_doc("Leave Type", leave_type)
    return leave_type_doc.one_fm_leave_payment_breakdown if leave_type_doc.one_fm_leave_payment_breakdown else False

def validate_leave_type_for_one_fm_paid_leave(doc, method):
    if doc.is_lwp:
        doc.one_fm_is_paid_sick_leave = False
        doc.one_fm_is_paid_annual_leave = False
    elif doc.one_fm_is_paid_sick_leave:
        doc.is_lwp = False
        doc.one_fm_is_paid_annual_leave = False
        doc.one_fm_is_hajj_leave = False
        if not doc.one_fm_paid_sick_leave_deduction_salary_component and not doc.one_fm_leave_payment_breakdown:
            frappe.throw(_('Either Paid Sick Leave Deduction Salary Component or Leave Payment Breakdown is Mandatory'))
    elif doc.one_fm_is_paid_annual_leave:
        doc.is_lwp = False
        doc.one_fm_is_paid_sick_leave = False
        doc.one_fm_is_hajj_leave = False
        if not doc.one_fm_annual_leave_allocation_reduction:
            frappe.throw(_('Annual Leave Allocation Reduction is Mandatory'))
    elif doc.one_fm_is_hajj_leave:
        doc.one_fm_is_paid_annual_leave = False
        doc.one_fm_is_hajj_leave = False

@frappe.whitelist(allow_guest=True)
def bereavement_leave_validation(doc, method):
    allocation = frappe.db.sql("select name from `tabLeave Allocation` where leave_type='Bereavement - وفاة' and employee='{0}' and docstatus=1 and '{1}' between from_date and to_date order by to_date desc limit 1".format(doc.employee, nowdate()))
    if allocation:
        allocation_doc = frappe.get_doc('Leave Allocation', allocation[0][0])
        allocation_doc.new_leaves_allocated = allocation_doc.new_leaves_allocated+doc.total_leave_days
        allocation_doc.total_leaves_allocated = allocation_doc.new_leaves_allocated+allocation_doc.unused_leaves
        allocation_doc.save()
        frappe.db.commit()
        print("Increase Bereavement leave balance for employee {0}".format(doc.employee))

        ledger = frappe._dict(
            doctype='Leave Ledger Entry',
            employee=doc.employee,
            leave_type='Bereavement - وفاة',
            transaction_type='Leave Allocation',
            transaction_name=allocation[0][0],
            leaves = doc.total_leave_days,
            from_date = allocation_doc.from_date,
            to_date = allocation_doc.to_date,
            is_carry_forward=0,
            is_expired=0,
            is_lwp=0
        )
        frappe.get_doc(ledger).submit()




@frappe.whitelist(allow_guest=True)
def update_employee_hajj_status(doc, method):
    if doc.leave_type and frappe.db.get_value('Leave Type', doc.leave_type, 'one_fm_is_hajj_leave') == 1:
        if method == "on_submit":
            frappe.db.set_value("Employee", doc.employee, 'went_to_hajj', True)
        if method == "on_cancel":
            frappe.db.set_value("Employee", doc.employee, 'went_to_hajj', False)

@frappe.whitelist(allow_guest=True)
def validate_hajj_leave(doc, method):
    if doc.leave_type and frappe.db.get_value('Leave Type', doc.leave_type, 'one_fm_is_hajj_leave') == 1:
        if frappe.db.get_value('Employee', doc.employee, 'went_to_hajj') == 1:
            frappe.throw(_("You can't apply for hajj leave twice"))

def get_salary(employee):
    salary_amount = 0

    salary_slip_name = frappe.db.sql("select name from `tabSalary Slip` where employee='{0}' order by creation desc limit 1".format(employee))
    if salary_slip_name:
        doc = frappe.get_doc('Salary Slip', salary_slip_name[0][0])

        for earning in doc.earnings:
            if earning.salary_component =='Basic':
                salary_amount = earning.amount

    else:
        doc = frappe.new_doc("Salary Slip")
        doc.payroll_frequency= "Monthly"
        doc.start_date=get_first_day(getdate(nowdate()))
        doc.end_date=get_last_day(getdate(nowdate()))
        doc.employee= str(employee)
        doc.posting_date= nowdate()
        doc.insert(ignore_permissions=True)

        if doc.name:
            for earning in doc.earnings:
                if earning.salary_component =='Basic':
                    salary_amount = earning.amount

            doc.delete()

    return salary_amount



@frappe.whitelist(allow_guest=True)
def hooked_leave_allocation_builder():
    emps = frappe.get_all("Employee",filters = {"status": "Active"}, fields = ["name", "date_of_joining","went_to_hajj"])
    for emp in emps:
        lts = frappe.get_list("Leave Type", fields = ["name","max_leaves_allowed"])
        for lt in lts:
            allocation_records = get_leave_allocation_records(nowdate(), emp.name, lt.name)

            if not allocation_records:
                allocation_from_date = ""
                allocation_to_date = ""
                new_leaves_allocated = 0
                if getdate(add_years(emp.date_of_joining,1)) > getdate(nowdate()):
                    allocation_from_date = emp.date_of_joining
                    allocation_to_date = add_days(add_years(emp.date_of_joining,1),-1)
                else:
                    day = "0" + str(getdate(emp.date_of_joining).day) if len(str(getdate(emp.date_of_joining).day)) == 1 else str(getdate(emp.date_of_joining).day)
                    month = "0" + str(getdate(emp.date_of_joining).month) if len(str(getdate(emp.date_of_joining).month)) == 1 else str(getdate(emp.date_of_joining).month)
                    year = str(getdate(nowdate()).year)

                    if getdate(emp.date_of_joining).month<=getdate(nowdate()).month:
                        if getdate(emp.date_of_joining).day<=getdate(nowdate()).day:
                            year = str(getdate(nowdate()).year)
                        else:
                            year = str(getdate(nowdate()).year-1)
                    else:
                        year = str(getdate(nowdate()).year-1)

                    allocation_from_date = year + "-" + month + "-" + day
                    allocation_to_date = add_days(add_years(allocation_from_date,1),-1)

                if lt.name == "Annual Leave - اجازة اعتيادية":
                    default_annual_leave_balance = frappe.db.get_value('Company', {"name": frappe.defaults.get_user_default("company")}, 'default_annual_leave_balance')
                    new_leaves_allocated = default_annual_leave_balance/365

                    su = frappe.new_doc("Leave Allocation")
                    su.update({
                        "leave_type": "Annual Leave - اجازة اعتيادية",
                        "employee": emp.name,
                        "from_date": allocation_from_date,
                        "to_date": allocation_to_date,
                        "carry_forward": 1,
                        "new_leaves_allocated": new_leaves_allocated
                        })
                    su.save(ignore_permissions=True)
                    su.submit()
                    frappe.db.commit()
                    print('New **Annual Leave - اجازة اعتيادية** for employee {0}'.format(emp.name))

                if lt.name == "Sick Leave - مرضية":
                    sl = frappe.new_doc("Leave Allocation")
                    sl.update({
                            "leave_type": "Sick Leave - مرضية",
                            "employee": emp.name,
                            "from_date": allocation_from_date,
                            "to_date": allocation_to_date,
                            "new_leaves_allocated": lt.max_leaves_allowed  #75
                            })
                    sl.save(ignore_permissions=True)
                    sl.submit()
                    frappe.db.commit()
                    print('New **Sick Leave - مرضية** for employee {0}'.format(emp.name))

                if lt.name == "Hajj leave - حج" and not emp.went_to_hajj:
                    sl = frappe.new_doc("Leave Allocation")
                    sl.update({
                            "leave_type": "Hajj leave - حج",
                            "employee": emp.name,
                            "from_date": allocation_from_date,
                            "to_date": allocation_to_date,
                            "new_leaves_allocated": lt.max_leaves_allowed  #21
                            })
                    sl.save(ignore_permissions=True)
                    sl.submit()
                    frappe.db.commit()
                    print('New **Hajj leave - حج** for employee {0}'.format(emp.name))

                if lt.name == "Bereavement - وفاة":
                    sl = frappe.new_doc("Leave Allocation")
                    sl.update({
                            "leave_type": "Bereavement - وفاة",
                            "employee": emp.name,
                            "from_date": allocation_from_date,
                            "to_date": allocation_to_date,
                            "new_leaves_allocated": lt.max_leaves_allowed  #150
                            })
                    sl.save(ignore_permissions=True)
                    sl.submit()
                    frappe.db.commit()
                    print('New **Bereavement - وفاة** for employee {0}'.format(emp.name))


def increase_daily_leave_balance():
    emps = frappe.get_all("Employee",filters = {"status": "Active"}, fields = ["name","annual_leave_balance"])
    for emp in emps:
        allocation = frappe.db.sql("select name from `tabLeave Allocation` where leave_type='Annual Leave - اجازة اعتيادية' and employee='{0}' and docstatus=1 and '{1}' between from_date and to_date order by to_date desc limit 1".format(emp.name,nowdate()))
        if allocation:
            if emp.annual_leave_balance>0:
                leave_balance = emp.annual_leave_balance/365
            else:
                default_annual_leave_balance = frappe.db.get_value('Company', {"name": frappe.defaults.get_user_default("company")}, 'default_annual_leave_balance')
                leave_balance = default_annual_leave_balance/365

            final_leave_balance = leave_balance

            allocation_records = get_leave_allocation_records(nowdate(), emp.name, 'Sick Leave - مرضية')
            allocation_from_date = allocation_records[emp.name]["Sick Leave - مرضية"].from_date
            allocation_to_date = allocation_records[emp.name]["Sick Leave - مرضية"].to_date

            attendance = frappe.db.sql_list("select attendance_date from `tabAttendance` where docstatus=1 and status='On Leave' and leave_type='Sick Leave - مرضية' and employee='{0}' and attendance_date between '{1}' and '{2}' ".format(emp.name, allocation_from_date, allocation_to_date))

            attendance_until_today = frappe.db.sql("select count(attendance_date) from `tabAttendance` where docstatus=1 and status='On Leave' and leave_type='Sick Leave - مرضية' and employee='{0}' and attendance_date between '{1}' and '{2}' ".format(emp.name, allocation_from_date, getdate(nowdate())))[0][0]

            if getdate(nowdate()) not in attendance:
                attendance_until_today = 0

            if attendance_until_today>=0 and attendance_until_today<=15:
                final_leave_balance = leave_balance
            elif attendance_until_today>15 and attendance_until_today<=25:
                final_leave_balance = leave_balance*0.75
            elif attendance_until_today>25 and attendance_until_today<=35:
                final_leave_balance = leave_balance*0.5
            elif attendance_until_today>35 and attendance_until_today<=45:
                final_leave_balance = leave_balance*0.25
            elif attendance_until_today>45 and attendance_until_today<=75:
                final_leave_balance = leave_balance*0.0

            print(attendance_until_today)
            print('******************************************')
            print(final_leave_balance)

            doc = frappe.get_doc('Leave Allocation', allocation[0][0])
            doc.new_leaves_allocated = doc.new_leaves_allocated+final_leave_balance
            doc.total_leaves_allocated = doc.new_leaves_allocated+doc.unused_leaves
            doc.save()
            frappe.db.commit()
            print("Increase daily leave balance for employee {0}".format(emp.name))

            ledger = frappe._dict(
                doctype='Leave Ledger Entry',
                employee=emp.name,
                leave_type='Annual Leave - اجازة اعتيادية',
                transaction_type='Leave Allocation',
                transaction_name=allocation[0][0],
                leaves = final_leave_balance,
                from_date = allocation_from_date,
                to_date = allocation_to_date,
                is_carry_forward=0,
                is_expired=0,
                is_lwp=0
            )
            frappe.get_doc(ledger).submit()


def get_leave_allocation_records(date, employee=None, leave_type=None):
    conditions = (" and employee='%s'" % employee) if employee else ""
    conditions += (" and leave_type='%s'" % leave_type) if leave_type else ""
    leave_allocation_records = frappe.db.sql("""
        select employee, leave_type, total_leaves_allocated, from_date, to_date
        from `tabLeave Allocation`
        where %s between from_date and to_date and docstatus=1 {0}""".format(conditions), (date), as_dict=1)

    allocated_leaves = frappe._dict()
    for d in leave_allocation_records:
        allocated_leaves.setdefault(d.employee, frappe._dict()).setdefault(d.leave_type, frappe._dict({
            "from_date": d.from_date,
            "to_date": d.to_date,
            "total_leaves_allocated": d.total_leaves_allocated
        }))

    return allocated_leaves


@frappe.whitelist(allow_guest=True)
def get_approved_leaves_for_period(employee, leave_type, from_date, to_date):
    #"
    leave_applications = frappe.db.sql("""
        select name,employee, leave_type, from_date, to_date, total_leave_days
        from `tabLeave Application`
        where employee=%(employee)s and leave_type=%(leave_type)s
            and docstatus=1 and status='Approved'
            and (from_date between %(from_date)s and %(to_date)s
                or to_date between %(from_date)s and %(to_date)s
                or (from_date < %(from_date)s and to_date > %(to_date)s))
    """, {
        "from_date": from_date,
        "to_date": to_date,
        "employee": employee,
        "leave_type": leave_type
    }, as_dict=1)

    leave_days = 0
    for leave_app in leave_applications:
        leave_days += leave_app.total_leave_days

    return leave_days



@frappe.whitelist()
def get_item_code(parent_item_group = None ,subitem_group = None ,item_group = None ,cur_item_id = None):
    item_code = None
    if parent_item_group:
        parent_item_group_code = frappe.db.get_value('Item Group', parent_item_group, 'item_group_code')
        item_code = parent_item_group_code

        if subitem_group:
            subitem_group_code = frappe.db.get_value('Item Group', subitem_group, 'item_group_code')
            item_code = parent_item_group_code+subitem_group_code

            if item_group:
                item_group_code = frappe.db.get_value('Item Group', item_group, 'item_group_code')
                item_code = parent_item_group_code+subitem_group_code+item_group_code

                if cur_item_id:
                    item_code = parent_item_group_code+subitem_group_code+item_group_code+cur_item_id

    return item_code


@frappe.whitelist(allow_guest=True)
def pam_salary_certificate_expiry_date():
    pam_salary_certificate = frappe.db.sql("select name,pam_salary_certificate_expiry_date from `tabPAM Salary Certificate`")
    for pam in pam_salary_certificate:
        date_difference = date_diff(pam[1], getdate(nowdate()))

        page_link = get_url("/desk#Form/PAM Salary Certificate/" + pam[0])
        setting = frappe.get_doc("PAM Salary Certificate Setting")

        if date_difference>0 and date_difference<setting.notification_start and date_difference%setting.notification_period == 0 :
            frappe.get_doc({
                "doctype":"ToDo",
                # "subject": "PAM salary certificate expiry date",
                "description": "PAM Salary Certificate will Expire after {0} day".format(date_difference),
                "reference_type": "PAM Salary Certificate",
                "reference_name": pam[0],
                "owner": 'omar.ja93@gmail.com',
                "date": pam[1]
            }).insert(ignore_permissions=True)

            print("PAM Salary Certificate will Expire after {0} day".format(date_difference))



@frappe.whitelist(allow_guest=True)
def pam_authorized_signatory():
    pam_authorized_signatory = frappe.db.sql("select name,authorized_signatory_expiry_date from `tabPAM Authorized Signatory List`")
    for pam in pam_authorized_signatory:
        date_difference = date_diff(pam[1], getdate(nowdate()))

        page_link = get_url("/desk#Form/PAM Authorized Signatory List/" + pam[0])
        setting = frappe.get_doc("PAM Authorized Signatory Setting")

        if date_difference>0 and date_difference<setting.notification_start and date_difference%setting.notification_period == 0 :
            frappe.get_doc({
                "doctype":"ToDo",
                # "subject": "PAM salary certificate expiry date",
                "description": "PAM Authorized Signatory will Expire after {0} day".format(date_difference),
                "reference_type": "PAM Authorized Signatory List",
                "reference_name": pam[0],
                "owner": 'omar.ja93@gmail.com',
                "date": pam[1]
            }).insert(ignore_permissions=True)

            print("PAM Authorized Signatory will Expire after {0} day".format(date_difference))




@frappe.whitelist(allow_guest=True)
def change_naming_series(doc, method):
    doc.name = doc.uom_abbreviation
