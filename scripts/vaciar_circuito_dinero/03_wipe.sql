-- ============================================================================
--  VACIAR EL CIRCUITO DE DINERO  (DESTRUCTIVO E IRREVERSIBLE)
--  Corré 01_backup.sh y 02_dry_run.sql ANTES.
--  Todo dentro de una transacción: si algo falla, no se aplica nada.
--
--  ALCANCE ELEGIDO: "Solo transacciones" + "Mantener maestros".
--    - Se borran ventas/compras/notas/caja (Paso A).
--    - Se limpian reservas de stock fantasma (Paso B) y los saldos acumulados
--      de proveedor que venían de esas transacciones (Paso C).
--    - Se CONSERVAN clientes/productos/proveedores y sus DEUDAS DE APERTURA
--      (deuda_inicial). ⇒ Un cliente/proveedor con saldo de apertura SEGUIRÁ
--      mostrando ese balance (no queda en 0). Para 0 absoluto, ver Paso D.
-- ============================================================================
BEGIN;

-- Paso A (obligatorio): borra ventas + compras + notas + caja.
-- RESTART IDENTITY reinicia los IDs; CASCADE resuelve el orden por FKs.
TRUNCATE TABLE
  pedidos,
  pedido_items,
  pago_imputaciones,
  pagos,
  bitacora_pedidos,
  rutas,
  ingresos_mercaderia,
  ingreso_mercaderia_items,
  pago_proveedor_imputaciones,
  pagos_proveedor,
  notas_proveedor,
  notas_credito_debito,
  nota_credito_items,
  cuenta_sanalle
RESTART IDENTITY CASCADE;

-- Paso B (ACTIVADO): limpiar reservas de stock fantasma que dejaban los pedidos
-- borrados. NO toca el stock disponible, solo los contadores de reservado.
UPDATE productos SET
  stock_reservado_a_cajas = 0, stock_reservado_a_blisters = 0,
  stock_reservado_b_cajas = 0, stock_reservado_b_blisters = 0;

-- Paso C (ACTIVADO): resetear los saldos ACUMULADOS de proveedores (venían de
-- las compras/pagos recién borrados). NO toca su deuda_inicial (apertura).
UPDATE proveedores SET saldo_remito = 0, saldo_factura = 0;

-- Paso D (DESACTIVADO — cuidado): arrancar de CERO ABSOLUTO también las deudas
-- iniciales (apertura) de clientes y proveedores. Por tu elección NO se tocan.
-- Descomentá SOLO si querés que los balances queden literalmente en 0:
-- UPDATE clientes    SET deuda_inicial = 0, deuda_inicial_remito = 0, deuda_inicial_factura = 0;
-- UPDATE proveedores SET deuda_inicial = 0;

-- Verificación dentro de la transacción (debería dar todo 0):
SELECT 'pedidos' AS tabla, count(*) FROM pedidos
UNION ALL SELECT 'pagos', count(*) FROM pagos
UNION ALL SELECT 'ingresos_mercaderia', count(*) FROM ingresos_mercaderia
UNION ALL SELECT 'cuenta_sanalle', count(*) FROM cuenta_sanalle;

-- Si los conteos son correctos, confirmá:
COMMIT;
-- Si algo se ve mal, en vez de COMMIT ejecutá:  ROLLBACK;
