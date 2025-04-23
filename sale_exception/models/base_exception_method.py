from odoo import models
from collections import defaultdict


class BaseExceptionMethod(models.AbstractModel):
    _inherit = "base.exception.method"

    def _get_exception_vals(self, vals = False):
        """List all exception_ids applied on self
        Exception ids are also written on records
        """
        if not vals:
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
        return all_exception_ids, vals
