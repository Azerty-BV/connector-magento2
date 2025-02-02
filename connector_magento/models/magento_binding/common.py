# © 2013-2019 Guewen Baconnier,Camptocamp SA,Akretion
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class MagentoBinding(models.AbstractModel):
    """Abstract Model for the Bindings.

    All the models used as bindings between Magento and Odoo
    (``magento.res.partner``, ``magento.product.product``, ...) should
    ``_inherit`` it.
    """

    _name = "magento.binding"
    _inherit = "external.binding"
    _description = "Magento Binding (abstract)"

    # odoo_id = odoo-side id must be declared in concrete model
    backend_id = fields.Many2one(
        comodel_name="magento.backend",
        string="Magento Backend",
        required=True,
        ondelete="restrict",
    )
    # fields.Char because 0 is a valid Magento ID
    external_id = fields.Char(string="ID on Magento")

    _sql_constraints = [
        (
            "magento_uniq",
            "unique(backend_id, external_id)",
            "A binding already exists with the same Magento ID.",
        ),
    ]

    @api.model
    def import_batch(self, backend, filters=None):
        """Prepare the import of records modified on Magento"""
        if filters is None:
            filters = {}
        with backend.work_on(self._name) as work:
            importer = work.component(usage="batch.importer")
            return importer.run(filters=filters)

    @api.model
    def import_record(self, backend, external_id, force=False):
        """Import a Magento record"""
        with backend.work_on(self._name) as work:
            importer = work.component(usage="record.importer")
            return importer.run(external_id, force=force)

    def export_record(self, fields=None):
        """Export a record on Magento"""
        self.ensure_one()
        with self.backend_id.work_on(self._name) as work:
            exporter = work.component(usage="record.exporter")
            return exporter.run(self, fields)

    def export_delete_record(self, backend, external_id):
        """Delete a record on Magento"""
        with backend.work_on(self._name) as work:
            deleter = work.component(usage="record.exporter.deleter")
            return deleter.run(external_id)
