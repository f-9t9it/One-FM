// Copyright (c) 2021, omar jaber and contributors
// For license information, please see license.txt

frappe.ui.form.on('PACI', {
	onload: function(frm) {
		if (!frm.is_new()){
            set_employee_details(frm);
        }
    },
    employee: function(frm){
        set_employee_details(frm);
    },
	apply_civil_id_online: function(frm){
		set_apply_civil_id_online(frm);

	},
	upload_civil_id_payment: function(frm){
		set_upload_civil_id_payment(frm);
	},
	upload_civil_id: function(frm){
		set_upload_civil_id(frm);
	},
	new_civil_id_expiry_date: function(frm){
		set_new_civil_id_expiry_date(frm);
	},

});
var set_employee_details = function(frm){
    if(frm.doc.employee){
        frappe.call({
            method:"frappe.client.get_value",//api calls
            args: {
                doctype:"Employee",
                filters: {
                name: frm.doc.employee
                },
                fieldname:["one_fm_first_name_in_arabic","one_fm_second_name_in_arabic","one_fm_third_name_in_arabic","one_fm_last_name_in_arabic",
				"first_name","middle_name","one_fm_third_name","last_name","one_fm_civil_id",
				"passport_number","one_fm_pam_designation","one_fm_nationality"]
            }, 
            callback: function(r) { 
        
                // set the returned value in a field
                frm.set_value('first_name_arabic', r.message.one_fm_first_name_in_arabic);
                frm.set_value('second_name_arabic', r.message.one_fm_second_name_in_arabic);
                frm.set_value('third_name_arabic', r.message.one_fm_third_name_in_arabic);
                frm.set_value('last_name_arabic', r.message.one_fm_last_name_in_arabic);
                frm.set_value('first_name_english',r.message.first_name);
                frm.set_value('second_name_english', r.message.middle_name);
                frm.set_value('third_name_english', r.message.one_fm_third_name);
                frm.set_value('last_name_english',r.message.last_name);
                frm.set_value('civil_id', r.message.one_fm_civil_id);
                frm.set_value('passport_number', r.message.passport_number);
                frm.set_value('pam_designation', r.message.one_fm_pam_designation);
                frm.set_value('nationality', r.message.one_fm_nationality);
               
            }
        })
    }
};
var set_apply_civil_id_online = function(frm)
{//1
	if(((frm.doc.apply_civil_id_online == "Yes") && (!frm.doc.apply_civil_id_online_datetime)))
	{
		// frappe.call({
		// 	method: 'one_fm.grd.doctype.paci.paci.set_dates',
		// 	callback: function(r)
		// 	{
		// 		if(r.message)
		// 		{
		// 			frm.set_value('apply_civil_id_online_datetime',r.message);
		// 		}
		// 	}
		// });
		frm.set_value('apply_civil_id_online_datetime',frappe.datetime.now_datetime())
	}
};
var set_upload_civil_id_payment = function(frm)
{//2
	if(((frm.doc.upload_civil_id_payment != null) && (!frm.doc.upload_civil_id_payment_datetime)))
	{
		
		frm.set_value('upload_civil_id_payment_datetime',frappe.datetime.now_datetime())
	}
};
var set_upload_civil_id = function(frm)
{//3
	if((frm.doc.upload_civil_id) && (!frm.doc.upload_civil_id_datetime))
	{
		
		frm.set_value('upload_civil_id_datetime',frappe.datetime.now_datetime())
	}
};
var set_new_civil_id_expiry_date = function(frm)
{//4
	if(((frm.doc.new_civil_id_expiry_date != null) && (!frm.doc.new_civil_id_expiry_date_update_time)))
	{
		
		frm.set_value('new_civil_id_expiry_date_update_time',frappe.datetime.now_datetime())
	}
};