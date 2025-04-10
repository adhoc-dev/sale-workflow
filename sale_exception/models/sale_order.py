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
        vals = self._get_exception_vals()
        lines = self.mapped("order_line")
        vals = lines._get_exception_vals()
        return vals

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
        vals = self.detect_exceptions()
        if vals:
            new_cr = Registry(self.env.cr.dbname).cursor()
            env = api.Environment(new_cr, self.env.uid, self.env.context)
            for records, values in vals.items():
                env[records._name].browse(records.id).write({'exception_ids': values})
            new_cr.commit()
            new_cr.close()
            # raise RedirectWarning(
            #     _('Exceptions'),
            #     self.env.ref('').id,
            #     _("Go to the configuration panel"),
            # )
            raise RedirectWarning(
                _('Ver excepciones'),
                {
                    'type': 'ir.actions.act_window',
                    'name': self.name,
                    'res_model': 'sale.exception.confirm',
                    'view_mode': 'form',
                    'res_id': False,
                    'target': 'new',
                    'context': {'active_ids': self.ids, 'active_model': 'sale.order'}
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

class BaseExceptionMethod(models.AbstractModel):
    _inherit = "base.exception.method"

    def _get_exception_vals(self):
        """List all exception_ids applied on self
        Exception ids are also written on records
        """
        vals = defaultdict(list)
        all_exception_ids, rules_to_remove, rules_to_add = self._get_exceptions()
        # Cumulate all the records to attach to the rule
        # before linking. We don't want to call "rule.write()"
        # which would:
        # * write on write_date so lock the exception.rule
        # * trigger the recomputation of "main_exception_id" on
        #   all the sale orders related to the rule, locking them all
        #   and preventing concurrent writes
        # Reversing the write by writing on SaleOrder instead of
        # ExceptionRule fixes the 2 kinds of unexpected locks.
        # It should not result in more queries than writing on ExceptionRule:
        # the "to remove" part generates one DELETE per rule on the relation
        # table 
        # and the "to add" part generates one INSERT (with unnest) per rule.
        for rule_id, records in rules_to_remove.items():
            vals[records].append((3, rule_id))
        for rule_id, records in rules_to_add.items():
            vals[records].append((4, rule_id))
        return vals
