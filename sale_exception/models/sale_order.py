# Copyright 2011 Akretion, Sodexis
# Copyright 2018 Akretion
# Copyright 2019 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, models, _
from odoo.modules.registry import Registry
from odoo.exceptions import RedirectWarning
from collections import defaultdict


class SaleOrder(models.Model):
    _inherit = ["sale.order", "base.exception"]
    _name = "sale.order"

    @api.model
    def _reverse_field(self):
        return "sale_ids"
    
    def detect_exceptions(self):
        all_exceptions = super().detect_exceptions()
        lines = self.mapped("order_line")
        all_exceptions += lines.detect_exceptions()
        return all_exceptions

    def detect_exceptions_vals(self):
        vals = defaultdict(list)
        order_exception_ids, vals = self._get_exception_vals(vals=vals)
        lines = self.mapped("order_line")
        line_exception_ids, vals = lines._get_exception_vals(vals=vals)       
        return order_exception_ids + line_exception_ids, vals

    @api.model
    def test_all_draft_orders(self):
        order_set = self.search([("state", "=", "draft")])
        order_set.detect_exceptions()
        return True

    def _fields_trigger_check_exception(self):
        return ["ignore_exception", "order_line", "state"]

    def _check_sale_check_exception(self, vals):
        check_exceptions = any(
            field in vals for field in self._fields_trigger_check_exception()
        )
        if check_exceptions:
            self.sale_check_exception()

    def write(self, vals):
        result = super().write(vals)
        self._check_sale_check_exception(vals)
        return result

    def sale_check_exception(self):
        orders = self.filtered(lambda s: s.state == "sale")
        if orders:
            orders._check_exception()

    def action_confirm(self):
        all_exception_ids, vals = self.filtered(lambda x: not x.ignore_exception).detect_exceptions_vals()
        if all_exception_ids:
            exception_text ='\n'.join([
                f"{exception['name']}: {exception['description']}" 
                for exception in self.env['exception.rule'].browse(all_exception_ids)]
            )
            if vals:
                new_cr = Registry(self.env.cr.dbname).cursor()
                env = api.Environment(new_cr, self.env.uid, self.env.context)
                for records, values in vals.items():
                    env[records._name].browse(records.id).write({'exception_ids': values})
                new_cr.commit()
                new_cr.close()
            raise RedirectWarning(
                exception_text,
                {
                    'type': 'ir.actions.act_window',
                    'name': self.name,
                    'res_model': 'sale.exception.confirm',
                    'views': [(False, 'form')],
                    'res_id': False,
                    'target': 'new',
                    'view_id': self.env.ref('sale_exception.view_sale_exception_confirm').id,
                    'context': {'active_id': self.id, 'active_ids': self.ids, 'active_model': 'sale.order'},
                },
                _("Go to the excepctions"),
            )

        return super().action_confirm()

    def action_draft(self):
        res = super().action_draft()
        orders = self.filtered("ignore_exception")
        orders.write({"ignore_exception": False})
        return res

    def _sale_get_lines(self):
        self.ensure_one()
        return self.order_line

    @api.model
    def _get_popup_action(self):
        return self.env.ref("sale_exception.action_sale_exception_confirm")

    def action_unlock(self):
        return super(
            SaleOrder, self.with_context(check_exception=False)
        ).action_unlock()
