
import coworking_app as core
import pyodbc
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="")
estado = {"bd": None}
o = lambda *a, **k: estado["bd"].opciones(*a, **k)


def err(e, codigo=400):
    msg = core.traducir_error(e) if isinstance(e, pyodbc.Error) else str(e)
    return jsonify(error=msg), codigo


def bd():
    if estado["bd"] is None:
        raise RuntimeError("Primero conéctate a SQL Server.")
    return estado["bd"]


def tabla_valida(t):
    if t not in bd().tablas():
        raise RuntimeError("Tabla no válida.")
    return t


@app.errorhandler(Exception)
def todos_los_errores(e):
    return err(e)


@app.route("/")
def inicio():
    return send_from_directory("static", "index.html")


@app.post("/api/login")
def login():
    d = request.json
    try:
        estado["bd"] = core.BD(core.conectar(d["servidor"].strip(), d.get("usuario", "").strip(), d.get("clave", "")))
    except Exception as e:  # noqa: BLE001
        t = core.limpiar_mensaje(e) if isinstance(e, pyodbc.Error) else str(e)
        return jsonify(error=f"{t}\n\nVerifica que SQL Server esté activo y que ya ejecutaste 01_script_coworking.sql."), 400
    return jsonify(ok=True, base=core.DB_NAME, tablas=estado["bd"].tablas())


# ------------------------- CRUD genérico -------------------------
@app.get("/api/tabla/<t>")
def tabla(t):
    b = bd(); tabla_valida(t)
    fks, listas = b.fks(t), b.listas_check(t)
    cols = []
    for c in b.columnas(t):
        n = c["nombre"]
        info = dict(c, obligatorio=(not c["nulo"]) and not c["identity"] and not c["default"], opciones=None)
        if n in fks:
            info["opciones"] = ([""] if c["nulo"] else []) + b.opciones(fks[n][0], col=fks[n][1]); info["fk"] = True
        elif n in listas:
            info["opciones"] = listas[n]
        cols.append(info)
    pk = b.pk(t)
    _, filas = b.consultar(f"SELECT * FROM {t} ORDER BY {pk}")
    return jsonify(columnas=cols, pk=pk, filas=[[core.formatear(v) for v in f] for f in filas])


def _limpio(v):
    v = (v or "").strip()
    return v or None


@app.post("/api/tabla/<t>")
def insertar(t):
    b = bd(); tabla_valida(t)
    datos = request.json
    pares = [(c["nombre"], _limpio(datos.get(c["nombre"]))) for c in b.columnas(t) if not c["identity"]]
    pares = [(n, v) for n, v in pares if v is not None]
    if not pares:
        raise RuntimeError("Completa el formulario para registrar.")
    b.ejecutar(f"INSERT INTO {t} ({', '.join(n for n, _ in pares)}) VALUES ({', '.join('?' for _ in pares)})",
               [v for _, v in pares])
    return jsonify(ok=True, mensaje="Registro creado correctamente.")


@app.put("/api/tabla/<t>/<ident>")
def actualizar(t, ident):
    b = bd(); tabla_valida(t)
    datos = request.json
    ed = [c for c in b.columnas(t) if not c["pk"] and not c["identity"]]
    sets = ", ".join(f"{c['nombre']} = ?" for c in ed)
    b.ejecutar(f"UPDATE {t} SET {sets} WHERE {b.pk(t)} = ?", [_limpio(datos.get(c["nombre"])) for c in ed] + [ident])
    return jsonify(ok=True, mensaje="Registro actualizado correctamente.")


@app.delete("/api/tabla/<t>/<ident>")
def eliminar(t, ident):
    b = bd(); tabla_valida(t)
    b.ejecutar(f"DELETE FROM {t} WHERE {b.pk(t)} = ?", [ident])
    return jsonify(ok=True, mensaje="Registro eliminado.")


# ------------------------- Reservas y pagos -------------------------
def _defs():
    return {
        "solicitudes": lambda: o("SOLICITUD", "WHERE estado_solicitud IN (N'Pendiente', N'Aprobada') "
                                              "AND id_solicitud NOT IN (SELECT id_solicitud FROM RESERVA)"),
        "condiciones": lambda: o("CONDICION_CONTRATACION"),
        "empleados": lambda: o("EMPLEADO", "WHERE estado_empleado = N'Activo'"),
        "reservas": lambda: o("RESERVA", "WHERE estado_reserva IN (N'Pendiente', N'Confirmada', N'En curso')"),
        "espacios": lambda: o("ESPACIO", "WHERE estado_espacio NOT IN (N'Mantenimiento', N'Inactivo')"),
        "metodos": lambda: o("METODO_PAGO"),
        "detalles": lambda: o("DETALLE_RESERVA", "WHERE estado_detalle IN (N'Reservado', N'En uso')"),
        "personas": lambda: o("PERSONA_AUTORIZADA"),
    }


OPERACIONES = [  # (título, ayuda, campos[(clave, etiqueta, tipo, fuente)], procedimiento)
    ("1. Crear reserva desde una solicitud", "Confirma una solicitud y genera su reserva con la condición de contratación elegida.",
     [("solicitud", "Solicitud", "combo", "solicitudes"), ("condicion", "Condición de contratación", "combo", "condiciones"),
      ("empleado", "Empleado responsable", "combo", "empleados")], "sp_crear_reserva"),
    ("2. Agregar un espacio a una reserva", "Calcula cantidad, precio y subtotal. Valida tarifa, vigencia y traslapes de horario.",
     [("reserva", "Reserva", "combo", "reservas"), ("espacio", "Espacio", "combo", "espacios"),
      ("tarifa", "Tarifa del espacio", "combo", "tarifas"), ("inicio", "Inicio (AAAA-MM-DD HH:MM)", "texto", None),
      ("fin", "Fin (AAAA-MM-DD HH:MM)", "texto", None), ("empleado", "Empleado responsable", "combo", "empleados")],
     "sp_agregar_detalle_reserva"),
    ("3. Registrar un pago", "No permite pagar más que el saldo pendiente de la reserva.",
     [("reserva", "Reserva", "combo", "reservas"), ("metodo", "Método de pago", "combo", "metodos"),
      ("monto", "Monto ($)", "texto", None), ("comprobante", "N.º de comprobante", "texto", None),
      ("empleado", "Empleado responsable", "combo", "empleados")], "sp_registrar_pago"),
    ("4. Cancelar una reserva", "Libera los espacios y calcula la penalidad según la condición contratada.",
     [("reserva", "Reserva", "combo", "reservas"), ("motivo", "Motivo de la cancelación", "texto", None),
      ("empleado", "Empleado responsable", "combo", "empleados")], "sp_cancelar_reserva"),
    ("5. Registrar acceso de una persona", "Solo pueden ingresar personas autorizadas en la reserva del espacio.",
     [("detalle", "Espacio reservado (detalle)", "combo", "detalles"), ("persona", "Persona autorizada", "combo", "personas")],
     "sp_registrar_acceso"),
]


@app.get("/api/operaciones")
def operaciones():
    bd(); fuentes = _defs(); cache = {}
    salida = []
    for i, (titulo, ayuda, campos, _p) in enumerate(OPERACIONES):
        cs = []
        for clave, etq, tipo, fuente in campos:
            if fuente and fuente != "tarifas":
                cache.setdefault(fuente, fuentes[fuente]())
            cs.append(dict(clave=clave, etiqueta=etq, tipo=tipo, depende="tarifa" if clave == "espacio" else None,
                           opciones=cache.get(fuente, []) if fuente != "tarifas" else []))
        salida.append(dict(indice=i, titulo=titulo, ayuda=ayuda, campos=cs))
    return jsonify(salida)


@app.get("/api/tarifas")
def tarifas():
    esp = request.args.get("espacio", "")
    return jsonify(o("TARIFA_ESPACIO", "WHERE id_espacio = ? AND estado_tarifa <> N'Inactiva'", (esp,)) if esp else [])


@app.post("/api/operaciones/<int:i>")
def ejecutar_operacion(i):
    b = bd()
    _t, _a, campos, proc = OPERACIONES[i]
    datos = request.json
    params = [_limpio(datos.get(c[0])) for c in campos]
    if any(p is None for p in params):
        raise RuntimeError("Completa todos los campos del formulario.")
    params = [p.split(" - ")[0] if c[2] == "combo" else p for p, c in zip(params, campos)]
    cols, filas = b.consultar(f"EXEC {proc} {', '.join('?' for _ in params)}", params)
    r = dict(zip(cols, filas[0])) if filas else {}
    mensajes = [
        lambda r: f"Reserva #{r.get('id_reserva')} creada y confirmada.",
        lambda r: f"Espacio agregado (detalle #{r.get('id_detalle_reserva')}). El total de la reserva se recalculó.",
        lambda r: f"Pago #{r.get('id_pago')} registrado. Saldo restante: ${r.get('saldo_restante')}",
        lambda r: f"Reserva #{r.get('id_reserva')} cancelada. Penalidad aplicable: ${r.get('penalidad_aplicable')}",
        lambda r: f"Acceso #{r.get('id_acceso')} registrado.",
    ]
    return jsonify(ok=True, mensaje=mensajes[i](r))


# ------------------------- Consultas -------------------------
@app.get("/api/consultas")
def consultas():
    bd()
    return jsonify(consultas=[dict(nombre=n, descripcion=d, parametrizada=(m == "disponibilidad"))
                              for n, d, _s, m in core.CONSULTAS],
                   sedes=[""] + o("SEDE"), tipos=[""] + o("TIPO_ESPACIO"))


@app.post("/api/consultas/<int:i>")
def correr_consulta(i):
    b = bd()
    _n, _d, sql, modo = core.CONSULTAS[i]
    p = request.json or {}
    params = ()
    if modo == "disponibilidad":
        idd = lambda t: t.split(" - ")[0] if t else None
        params = (p.get("inicio", "").strip(), p.get("fin", "").strip(), idd(p.get("sede")), idd(p.get("tipo")))
    cols, filas = b.consultar(sql, params)
    return jsonify(columnas=cols, filas=[[core.formatear(v) for v in f] for f in filas])


if __name__ == "__main__":
    print("Abre http://localhost:5000 en tu navegador")
    app.run(port=5000, debug=False)
