-- DRY-RUN: cuenta cuántas filas se borrarían. NO borra nada.
SELECT 'pedidos'                    AS tabla, count(*) FROM pedidos
UNION ALL SELECT 'pedido_items',                 count(*) FROM pedido_items
UNION ALL SELECT 'pago_imputaciones',            count(*) FROM pago_imputaciones
UNION ALL SELECT 'pagos',                        count(*) FROM pagos
UNION ALL SELECT 'bitacora_pedidos',             count(*) FROM bitacora_pedidos
UNION ALL SELECT 'rutas',                        count(*) FROM rutas
UNION ALL SELECT 'ingresos_mercaderia',          count(*) FROM ingresos_mercaderia
UNION ALL SELECT 'ingreso_mercaderia_items',     count(*) FROM ingreso_mercaderia_items
UNION ALL SELECT 'pago_proveedor_imputaciones',  count(*) FROM pago_proveedor_imputaciones
UNION ALL SELECT 'pagos_proveedor',              count(*) FROM pagos_proveedor
UNION ALL SELECT 'notas_proveedor',              count(*) FROM notas_proveedor
UNION ALL SELECT 'notas_credito_debito',         count(*) FROM notas_credito_debito
UNION ALL SELECT 'nota_credito_items',           count(*) FROM nota_credito_items
UNION ALL SELECT 'cuenta_sanalle',               count(*) FROM cuenta_sanalle
ORDER BY tabla;

-- Referencia (NO se tocan): estas quedan como están
SELECT 'clientes (se conservan)' AS info, count(*) FROM clientes
UNION ALL SELECT 'productos (se conservan)', count(*) FROM productos;
