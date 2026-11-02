# -*- coding: utf-8 -*-
import base64
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.stock_kardex_adjustment_jeal.hooks import mark_existing_moves
from .test_kardex_adjustment import KardexAdjustmentCommon


@tagged('post_install', '-at_install')
class TestKardexMarkAndPle(KardexAdjustmentCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = cls.categ
        while root.parent_id:
            root = root.parent_id
        root.kardex_stock_type = '01'
        cls.categ.kardex_stock_type = '03'

    def _ple_run(self):
        return self._run(filter_product_ids=[(5, 0, 0)])

    def _txt_lines(self, run, book):
        content = base64.b64decode(run['ple_%s_txt' % book]).decode('utf-8')
        self.assertTrue(content.endswith('\r\n'))
        lines = [line.split('|') for line in content.split('\r\n') if line]
        return [fields for fields in lines if fields[6] == 'CO-TEST']

    # ------------------------------------------------------------------
    # Marca de los asientos (2)
    # ------------------------------------------------------------------
    def test_adjustment_moves_are_marked(self):
        out = self._scenario()
        run = self._run()
        run.action_generate()
        line = self._posted_lines()
        move = line.move_id
        self.assertTrue(move.kardex_adjustment)
        self.assertEqual(move.kardex_adjustment_type, 'cost')
        self.assertEqual(move.kardex_adjustment_run_id, run)
        self.assertEqual(move.kardex_adjusted_layer_id, line.adjusted_layer_id)
        self.assertEqual(move.kardex_adjusted_stock_move_id, out)
        self.assertTrue(all(move.line_ids.mapped('kardex_adjustment')))
        self.assertEqual(set(move.line_ids.mapped('kardex_adjustment_type')), {'cost'})
        # Filtros de Apuntes contables
        AML = self.env['account.move.line']
        self.assertEqual(AML.search([('kardex_adjustment', '=', True)]).move_id, move)
        self.assertNotIn(move, AML.search([('kardex_adjustment', '=', False)]).move_id)
        groups = AML._read_group([('kardex_adjustment', '=', True)], ['kardex_adjustment_type'], ['__count'])
        self.assertEqual(groups, [('cost', 2)])
        # No editable por el usuario
        self.assertTrue(self.env['account.move']._fields['kardex_adjustment'].readonly)

    def test_reversal_is_marked(self):
        out = self._scenario()
        self._run().action_generate()
        line = self._posted_lines()
        self._set_entry_date(out, date(2026, 1, 5))
        run = self._run()
        run.action_generate()
        reversal = line.reversal_move_ids
        self.assertTrue(reversal.kardex_adjustment)
        self.assertEqual(reversal.kardex_adjustment_type, 'cost')
        self.assertEqual(reversal.kardex_adjustment_run_id, run)
        self.assertEqual(reversal.reversed_entry_id, line.move_id)

    def test_script_marks_existing_moves(self):
        self._scenario()
        self._run().action_generate()
        line = self._posted_lines()
        self.env.cr.execute(
            "UPDATE account_move SET kardex_adjustment = NULL, kardex_adjustment_type = NULL, "
            "kardex_adjustment_run_id = NULL, kardex_adjusted_layer_id = NULL WHERE id = %s",
            [line.move_id.id])
        self.env.cr.execute(
            "UPDATE account_move_line SET kardex_adjustment = NULL, kardex_adjustment_type = NULL "
            "WHERE move_id = %s", [line.move_id.id])
        self.env.invalidate_all()
        self.assertFalse(line.move_id.kardex_adjustment)
        mark_existing_moves(self.env.cr)
        self.env.invalidate_all()
        self.assertTrue(line.move_id.kardex_adjustment)
        self.assertEqual(line.move_id.kardex_adjustment_type, 'cost')
        self.assertEqual(line.move_id.kardex_adjustment_run_id, line.run_id)
        self.assertEqual(set(line.move_id.line_ids.mapped('kardex_adjustment_type')), {'cost'})

    def test_balance_columns_not_summed_when_grouped(self):
        Row = self.env['stock.kardex.adjustment.row']
        for name in ('bal_qty', 'bal_value', 'raw_bal_value', 'recalc_value'):
            self.assertFalse(Row._fields[name].aggregator, name)
        self.assertEqual(Row._fields['adjust_value'].aggregator, 'sum')

    # ------------------------------------------------------------------
    # Libros 13.1 y 12.1 (3 y 4)
    # ------------------------------------------------------------------
    def test_ple_requires_registered_adjustments(self):
        self._scenario()
        run = self._ple_run()
        run.action_compute()
        self.assertEqual(run.state, 'computed')
        with self.assertRaises(UserError):
            run.action_generate_ple_131()
        filtered = self._run()
        filtered.action_generate()
        with self.assertRaises(UserError):
            filtered.action_generate_ple_131()

    def test_ple_131(self):
        self._scenario()
        run = self._ple_run()
        run.action_generate()
        self.assertEqual(run.state, 'done')
        run.action_generate_ple_131()
        vat = ''.join(c for c in (self.company.vat or '') if c.isalnum())
        self.assertEqual(run.ple_131_txt_name, 'LE%s20260100130100001111.txt' % vat
                         if self.company.currency_id.name == 'PEN'
                         else 'LE%s20260100130100001121.txt' % vat)
        self.assertTrue(run.ple_131_xlsx)
        self.assertTrue(run.ple_131_pdf)
        lines = self._txt_lines(run, '131')
        # Saldo inicial, recepción 2/1, recepción 10/1, salida 20/1 y su ajuste
        self.assertEqual(len(lines), 5)
        for fields in lines:
            self.assertEqual(len(fields), 28, 'Campos 1-27 terminados en |')
            self.assertEqual(fields[27], '')
            self.assertEqual(fields[0], '20260100')
            self.assertIn(fields[2][:1], ('A', 'M'))
            self.assertEqual(fields[3], '0000')
            self.assertEqual(fields[5], '03')
            self.assertEqual(fields[15], 'NIU')
            self.assertEqual(fields[16], '1')
            self.assertEqual(fields[26], '1')
        opening, in1, in2, out, adj = lines
        self.assertEqual((opening[2], opening[13]), ('A000000001', '16'))
        self.assertEqual(in1[9], '02/01/2026')
        self.assertEqual((in1[17], in1[19]), ('10.00', '1000.00'))
        self.assertEqual(in1[13], '02')
        # Salida: cantidad y costo total negativos, costo unitario positivo
        self.assertEqual((out[20], out[21], out[22]), ('-5.00', '100.00000000', '-500.00'))
        # Salida a clientes sin orden de venta: ajuste de inventario (R12)
        self.assertEqual(out[13], '28')
        # Ajuste: tipo 00, operación 99, cantidad 0, importe en costo total de Salida
        line = self._posted_lines()
        self.assertEqual(adj[1], ''.join(c for c in line.move_id.name if c.isalnum()))
        self.assertEqual((adj[10], adj[13]), ('00', '99'))
        self.assertEqual(adj[11], ''.join(c for c in line.move_id.journal_id.code if c.isalnum()))
        self.assertEqual(adj[9], '20/01/2026')
        self.assertEqual((adj[17], adj[18], adj[19]), ('0.00', '0.00', '0.00'))
        self.assertEqual((adj[20], adj[21], adj[22]), ('0.00', '0.00', '-75.00'))
        self.assertEqual((adj[23], adj[24], adj[25]), ('15.00', '115.00000000', '1725.00'))
        self.assertIn('El saldo final de cada existencia es igual a su saldo contable', run.ple_message)

    def test_ple_121(self):
        self._scenario()
        run = self._ple_run()
        run.action_generate()
        run.action_generate_ple_121()
        self.assertTrue(run.ple_121_txt_name.startswith('LE'))
        self.assertIn('120100', run.ple_121_txt_name)
        self.assertTrue(run.ple_121_xlsx)
        self.assertTrue(run.ple_121_pdf)
        lines = self._txt_lines(run, '121')
        # Sin la línea de ajuste: solo movimientos con unidades
        self.assertEqual(len(lines), 4)
        for fields in lines:
            self.assertEqual(len(fields), 20, 'Campos 1-19 terminados en |')
            self.assertEqual(fields[18], '1')
            self.assertTrue(fields[16] == '0.00' or fields[17] == '0.00', 'Campos 17 y 18 excluyentes')
        self.assertEqual([f[16] for f in lines], ['0.00', '10.00', '10.00', '0.00'])
        self.assertEqual([f[17] for f in lines], ['0.00', '0.00', '0.00', '-5.00'])
        self.assertIn('coinciden con las del 13.1', run.ple_message)
