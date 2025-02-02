# Copyright 2014-2019 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from .common import MagentoSyncTestCase, recorder


class TestExportPicking(MagentoSyncTestCase):
    """Test the export of pickings to Magento"""

    def setUp(self):
        super(TestExportPicking, self).setUp()
        # import a sales order
        self.order_binding = self._import_record("magento.sale.order", 100000201)
        self.order_binding.ignore_exception = True
        # generate sale's picking
        self.order_binding.odoo_id.action_confirm()
        # Create inventory for add stock qty to lines
        # With this commit https://goo.gl/fRTLM3 the moves that where
        # force-assigned are not transferred in the picking
        for line in self.order_binding.odoo_id.order_line:
            if line.product_id.type == "product":
                inventory = self.env["stock.inventory"].create(
                    {
                        "name": "Inventory for line %s" % line.name,
                        # 'filter': 'product',
                        "product_ids": [[6, 0, line.product_id.ids]],
                        "line_ids": [
                            (
                                0,
                                0,
                                {
                                    "product_id": line.product_id.id,
                                    "product_qty": line.product_uom_qty,
                                    "location_id": self.env.ref(
                                        "stock.stock_location_stock"
                                    ).id,
                                },
                            )
                        ],
                    }
                )
                inventory._action_start()
                inventory.action_validate()
        self.picking = self.order_binding.picking_ids
        self.assertEqual(len(self.picking), 1)
        magento_shop = self.picking.sale_id.magento_bind_ids[0].store_id
        magento_shop.send_picking_done_mail = True

    def test_export_complete_picking_trigger(self):
        """Trigger export of a complete picking"""
        self.picking.action_assign()
        with self.mock_with_delay() as (delayable_cls, delayable):
            # Deliver the entire picking, a 'magento.stock.picking'
            # should be created, then a job is generated that will export
            # the picking. Here the job is not created because we mock
            # 'with_delay()'
            self.env["stock.immediate.transfer"].create(
                {"pick_ids": [(4, self.picking.id)]}
            ).process()
            self.assertEqual(self.picking.state, "done")

            picking_binding = self.env["magento.stock.picking"].search(
                [
                    ("odoo_id", "=", self.picking.id),
                    ("backend_id", "=", self.backend.id),
                ],
            )
            self.assertEqual(1, len(picking_binding))
            self.assertEqual("complete", picking_binding.picking_method)

            self.assertEqual(1, delayable_cls.call_count)
            delay_args, delay_kwargs = delayable_cls.call_args
            self.assertEqual((picking_binding,), delay_args)

            delayable.export_picking_done.assert_called_with(with_tracking=False)

    def test_export_complete_picking_job(self):
        """Exporting a complete picking"""
        self.picking.action_assign()
        with self.mock_with_delay():
            # Deliver the entire picking, a 'magento.stock.picking'
            # should be created, then a job is generated that will export
            # the picking. Here the job is not created because we mock
            # 'with_delay()'
            self.env["stock.immediate.transfer"].create(
                {"pick_ids": [(4, self.picking.id)]}
            ).process()
            self.assertEqual(self.picking.state, "done")
            picking_binding = self.env["magento.stock.picking"].search(
                [
                    ("odoo_id", "=", self.picking.id),
                    ("backend_id", "=", self.backend.id),
                ],
            )
            self.assertEqual(1, len(picking_binding))

        with recorder.use_cassette("test_export_picking_complete") as cassette:
            picking_binding.export_picking_done(with_tracking=False)

        # 1. login, 2. sales_order_shipment.create,
        # 3. endSession
        self.assertEqual(3, len(cassette.requests))

        self.assertEqual(
            (
                "sales_order_shipment.create",
                ["100000201", {}, "Shipping Created", True, True],
            ),
            self.parse_cassette_request(cassette.requests[1].body),
        )

        # Check that we have received and bound the magento ID
        self.assertEqual(picking_binding.external_id, "987654321")

    def test_export_partial_picking_trigger(self):
        """Trigger export of a partial picking"""
        # Prepare a partial picking
        # The sale order contains 2 lines with 1 product each
        self.picking.action_assign()
        self.picking.move_lines[0].quantity_done = 1
        self.picking.move_lines[1].quantity_done = 0
        # Remove reservation for line index 1
        self.picking.move_lines[1].move_line_ids.unlink()

        with self.mock_with_delay() as (delayable_cls, delayable):
            # Deliver the entire picking, a 'magento.stock.picking'
            # should be created, then a job is generated that will export
            # the picking. Here the job is not created because we mock
            # 'with_delay()'
            backorder_action = self.picking.button_validate()
            self.assertEqual(
                backorder_action["res_model"],
                "stock.backorder.confirmation",
                "A backorder confirmation wizard action must be created",
            )
            # Confirm backorder creation
            self.env["stock.backorder.confirmation"].browse(
                backorder_action["res_id"]
            ).process()

            self.assertEqual(self.picking.state, "done")

            picking_binding = self.env["magento.stock.picking"].search(
                [
                    ("odoo_id", "=", self.picking.id),
                    ("backend_id", "=", self.backend.id),
                ],
            )
            self.assertEqual(1, len(picking_binding))
            self.assertEqual("partial", picking_binding.picking_method)

            self.assertEqual(1, delayable_cls.call_count)
            delay_args, delay_kwargs = delayable_cls.call_args
            self.assertEqual((picking_binding,), delay_args)

            delayable.export_picking_done.assert_called_with(with_tracking=False)

    def test_export_partial_picking_job(self):
        """Exporting a partial picking"""
        # Prepare a partial picking
        # The sale order contains 2 lines with 1 product each
        self.picking.action_assign()
        self.picking.move_lines[0].quantity_done = 1
        self.picking.move_lines[1].quantity_done = 0

        with self.mock_with_delay():
            # Deliver the entire picking, a 'magento.stock.picking'
            # should be created, then a job is generated that will export
            # the picking. Here the job is not created because we mock
            # 'with_delay()'
            self.env["stock.backorder.confirmation"].create(
                {"pick_ids": [(4, self.picking.id)]}
            ).process()
            self.assertEqual(self.picking.state, "done")
            picking_binding = self.env["magento.stock.picking"].search(
                [
                    ("odoo_id", "=", self.picking.id),
                    ("backend_id", "=", self.backend.id),
                ],
            )
            self.assertEqual(1, len(picking_binding))

        with recorder.use_cassette("test_export_picking_partial") as cassette:
            picking_binding.export_picking_done(with_tracking=False)

        # 1. login, 2. sales_order_shipment.create,
        # 3. endSession
        self.assertEqual(3, len(cassette.requests))

        self.assertEqual(
            (
                "sales_order_shipment.create",
                ["100000201", {"543": 1.0}, "Shipping Created", True, True],
            ),
            self.parse_cassette_request(cassette.requests[1].body),
        )

        # Check that we have received and bound the magento ID
        self.assertEqual(picking_binding.external_id, "987654321")

    def test_export_tracking_after_done_trigger(self):
        """Trigger export of a tracking number"""
        self.picking.action_assign()

        with self.mock_with_delay():
            self.env["stock.immediate.transfer"].create(
                {"pick_ids": [(4, self.picking.id)]}
            ).process()
            self.assertEqual(self.picking.state, "done")

        picking_binding = self.env["magento.stock.picking"].search(
            [("odoo_id", "=", self.picking.id), ("backend_id", "=", self.backend.id)],
        )
        self.assertEqual(1, len(picking_binding))

        with self.mock_with_delay() as (delayable_cls, delayable):
            self.picking.carrier_tracking_ref = "XYZ"

            self.assertEqual(1, delayable_cls.call_count)
            delay_args, delay_kwargs = delayable_cls.call_args
            self.assertEqual((picking_binding,), delay_args)

            delayable.export_tracking_number.assert_called_with()

    def test_export_tracking_after_done_job(self):
        """Job export of a tracking number"""
        self.picking.action_assign()

        with self.mock_with_delay():
            self.env["stock.immediate.transfer"].create(
                {"pick_ids": [(4, self.picking.id)]}
            ).process()
            self.assertEqual(self.picking.state, "done")
            self.picking.carrier_tracking_ref = "XYZ"

        picking_binding = self.env["magento.stock.picking"].search(
            [("odoo_id", "=", self.picking.id), ("backend_id", "=", self.backend.id)],
        )
        self.assertEqual(1, len(picking_binding))
        picking_binding.external_id = "100000035"

        with recorder.use_cassette("test_export_tracking_number") as cassette:
            picking_binding.export_tracking_number()

        # 1. login, 2. sales_order_shipment.getCarriers,
        # 3. sales_order_shipment.addTrack, 4. endSession
        self.assertEqual(4, len(cassette.requests))

        self.assertEqual(
            ("sales_order_shipment.getCarriers", ["100000201"]),
            self.parse_cassette_request(cassette.requests[1].body),
        )

        self.assertEqual(
            ("sales_order_shipment.addTrack", ["100000035", "ups", "", "XYZ"]),
            self.parse_cassette_request(cassette.requests[2].body),
        )
