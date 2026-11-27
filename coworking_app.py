
import datetime as dt
import os
import re
import sys
import tkinter as tk
from tkinter import messagebox, ttk

try:
    import pyodbc
except ImportError:
    print("Falta la librería pyodbc. Instálala con:  pip install pyodbc")
    sys.exit(1)

DB_NAME = "CoworkingDB"

ORDEN_TABLAS = [
    "SEDE", "TIPO_ESPACIO", "CARACTERISTICA", "ESPACIO", "ESPACIO_CARACTERISTICA",
    "TARIFA_ESPACIO", "USUARIO", "CONDICION_CONTRATACION", "SOLICITUD", "RESERVA",
    "DETALLE_RESERVA", "SERVICIO_ADICIONAL", "RESERVA_SERVICIO", "METODO_PAGO", "PAGO",
    "PERSONA_AUTORIZADA", "EMPLEADO", "ACCESO", "HISTORIAL", "NOVEDAD",
]

# Texto que se muestra al elegir un registro referenciado por una llave foránea
ETIQUETAS = {
    "SEDE": "nombre_sede",
    "TIPO_ESPACIO": "nombre_tipo_espacio",
    "CARACTERISTICA": "nombre_caracteristica",
    "ESPACIO": "nombre_espacio",
    "USUARIO": "nombre_usuario + N' ' + apellido_usuario",
    "EMPLEADO": "nombre_empleado + N' ' + apellido_empleado + N' (' + cargo_empleado + N')'",
    "PERSONA_AUTORIZADA": "nombre_persona + N' ' + apellido_persona + N' (reserva ' + CAST(id_reserva AS NVARCHAR(10)) + N')'",
    "METODO_PAGO": "nombre_metodo_pago",
    "SERVICIO_ADICIONAL": "nombre_servicio",
    "CONDICION_CONTRATACION": "nombre_condicion",
    "SOLICITUD": "CONCAT(N'Solicitud #', id_solicitud, N' | ', CONVERT(NVARCHAR(16), fecha_inicio_solicitud, 120), N' | ', estado_solicitud)",
    "RESERVA": "CONCAT(N'Reserva #', id_reserva, N' | ', estado_reserva, N' | $', total_reserva)",
    "DETALLE_RESERVA": "CONCAT(N'Detalle #', id_detalle_reserva, N' | reserva ', id_reserva, N' | espacio ', id_espacio, N' | ', CONVERT(NVARCHAR(16), fecha_inicio, 120), N' | ', estado_detalle)",
    "TARIFA_ESPACIO": "CONCAT(N'Espacio ', id_espacio, N' | ', unidad_tiempo, N' | $', precio_tarifa, N' | ', estado_tarifa)",
}

CONSULTAS = [
    ("1. Ocupación e ingresos por sede",
     "¿Qué sedes concentran más espacios reservados, horas contratadas e ingresos?",
     "SELECT * FROM vw_ocupacion_por_sede ORDER BY ingresos_espacios DESC", None),
    ("2. Ingresos por tipo de espacio y mes",
     "¿Qué tipos de espacio generan más ingresos en cada mes?",
     "SELECT * FROM vw_ingresos_por_tipo_mes ORDER BY periodo, ingresos DESC", None),
    ("3. Reservas con saldo pendiente",
     "¿Qué clientes tienen pagos pendientes y de cuánto es el saldo?",
     "SELECT * FROM vw_reservas_con_saldo ORDER BY saldo_pendiente DESC", None),
    ("4. Ranking de clientes",
     "¿Quiénes son los clientes que más reservan y consumen?",
     "SELECT * FROM vw_ranking_clientes ORDER BY total_consumido DESC", None),
    ("5. Servicios adicionales más contratados",
     "¿Qué servicios adicionales se venden más y cuánto ingreso generan?",
     "SELECT * FROM vw_servicios_mas_contratados ORDER BY ingresos_servicio DESC", None),
    ("6. Novedades pendientes de resolver",
     "¿Qué incidencias siguen abiertas, en qué sede y con qué prioridad?",
     "SELECT * FROM vw_novedades_pendientes ORDER BY dias_abierta DESC", None),
    ("7. Cancelaciones y penalidades",
     "¿Qué reservas se cancelaron y qué penalidad corresponde según la condición contratada?",
     "SELECT * FROM vw_cancelaciones_penalidad ORDER BY fecha_cancelacion DESC", None),
    ("8. Espacios disponibles en un rango (parametrizada)",
     "¿Qué espacios están libres entre dos fechas? Evita conflictos de disponibilidad.",
     "EXEC sp_espacios_disponibles ?, ?, ?, ?", "disponibilidad"),
]

COLOR_PRIMARIO = "#1f2d3d"
COLOR_ACENTO = "#f28c28"
COLOR_FONDO = "#f4f6f9"


# ----------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------
def limpiar_mensaje(e):
    """Quita los prefijos del driver ODBC y deja solo el mensaje de SQL Server."""
    texto = str(e.args[1]) if len(e.args) > 1 else str(e)
    texto = re.sub(r"^(\[[^\]]*\]\s*)+", "", texto)
    texto = re.sub(r"(\s*\(\d+\))*\s*(\(SQL\w+\))?\s*$", "", texto)
    return texto.strip()


def traducir_error(e):
    """Devuelve un mensaje claro en español para el usuario."""
    crudo = str(e.args[1]) if len(e.args) > 1 else str(e)
    numeros = re.findall(r"\((\d+)\)", crudo)
    numero = int(numeros[-1]) if numeros else 0
    detalle = limpiar_mensaje(e)
    if numero >= 50000:  # errores propios del sistema (THROW)
        return detalle
    if numero == 547:
        if "DELETE" in crudo.upper() and "REFERENCE" in crudo.upper():
            return ("No se puede eliminar: el registro está siendo usado por otras tablas.\n\n" + detalle)
        if "CHECK" in crudo.upper():
            return "Un valor no cumple una regla de validación (CHECK).\n\n" + detalle
        return "La referencia (llave foránea) indicada no existe.\n\n" + detalle
    if numero in (2627, 2601):
        return "Ya existe un registro con esos datos (restricción de unicidad).\n\n" + detalle
    if numero == 515:
        return "Hay un campo obligatorio vacío.\n\n" + detalle
    if numero in (241, 242, 245, 8114):
        return "Algún dato tiene un formato incorrecto (fecha, hora o número).\n\n" + detalle
    return detalle


def conectar(servidor, usuario, clave):
    drivers = [d for d in pyodbc.drivers() if "SQL Server" in d]
    if not drivers:
        raise RuntimeError(
            "No hay ningún driver ODBC de SQL Server instalado.\n"
            "Instala 'ODBC Driver 17 (o 18) for SQL Server' de Microsoft.")

    def rango(d):
        m = re.search(r"ODBC Driver (\d+)", d)
        return int(m.group(1)) if m else 0

    driver = max(drivers, key=rango)
    cadena = f"DRIVER={{{driver}}};SERVER={servidor};DATABASE={DB_NAME};"
    cadena += f"UID={usuario};PWD={clave};" if usuario else "Trusted_Connection=yes;"
    if rango(driver) >= 17:
        cadena += "Encrypt=no;TrustServerCertificate=yes;"
    return pyodbc.connect(cadena, autocommit=True, timeout=8)


# ----------------------------------------------------------------------
# Acceso a datos
# ----------------------------------------------------------------------
class BD:
    def __init__(self, conexion):
        self.conn = conexion
        self._cols = {}

    def consultar(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(sql, params)
        while cur.description is None:
            if not cur.nextset():
                return [], []
        columnas = [c[0] for c in cur.description]
        filas = [tuple(f) for f in cur.fetchall()]
        return columnas, filas

    def ejecutar(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(sql, params)

    def tablas(self):
        _, filas = self.consultar("SELECT name FROM sys.tables")
        existentes = {f[0] for f in filas}
        ordenadas = [t for t in ORDEN_TABLAS if t in existentes]
        return ordenadas + sorted(existentes - set(ordenadas))

    def columnas(self, tabla):
        if tabla in self._cols:
            return self._cols[tabla]
        sql = """
        SELECT c.name, t.name, c.is_nullable, c.is_identity,
               CASE WHEN pk.column_id IS NULL THEN 0 ELSE 1 END,
               CASE WHEN c.default_object_id <> 0 THEN 1 ELSE 0 END
        FROM sys.columns c
        JOIN sys.types t ON t.user_type_id = c.user_type_id
        LEFT JOIN (SELECT ic.object_id, ic.column_id
                     FROM sys.indexes i
                     JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
                    WHERE i.is_primary_key = 1) pk
               ON pk.object_id = c.object_id AND pk.column_id = c.column_id
        WHERE c.object_id = OBJECT_ID(?)
        ORDER BY c.column_id"""
        _, filas = self.consultar(sql, (f"dbo.{tabla}",))
        cols = [dict(nombre=f[0], tipo=f[1], nulo=bool(f[2]), identity=bool(f[3]),
                     pk=bool(f[4]), default=bool(f[5])) for f in filas]
        self._cols[tabla] = cols
        return cols

    def pk(self, tabla):
        for c in self.columnas(tabla):
            if c["pk"]:
                return c["nombre"]
        return self.columnas(tabla)[0]["nombre"]

    def fks(self, tabla):
        sql = """
        SELECT pc.name, OBJECT_NAME(fkc.referenced_object_id), rc.name
        FROM sys.foreign_key_columns fkc
        JOIN sys.columns pc ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
        JOIN sys.columns rc ON rc.object_id = fkc.referenced_object_id AND rc.column_id = fkc.referenced_column_id
        WHERE fkc.parent_object_id = OBJECT_ID(?)"""
        _, filas = self.consultar(sql, (f"dbo.{tabla}",))
        return {f[0]: (f[1], f[2]) for f in filas}

    def listas_check(self, tabla):
        """Valores permitidos por las restricciones CHECK de tipo lista (estados)."""
        sql = """
        SELECT c.name, cc.definition
        FROM sys.check_constraints cc
        JOIN sys.columns c ON c.object_id = cc.parent_object_id AND c.column_id = cc.parent_column_id
        WHERE cc.parent_object_id = OBJECT_ID(?) AND cc.parent_column_id > 0"""
        _, filas = self.consultar(sql, (f"dbo.{tabla}",))
        listas = {}
        for nombre, definicion in filas:
            if re.search(r"\[%s\]\s*=\s*N?'" % re.escape(nombre), definicion):
                listas[nombre] = re.findall(r"=\s*N?'([^']*)'", definicion)
        return listas

    def opciones(self, tabla, where="", params=(), col=None):
        col = col or self.pk(tabla)
        expr = ETIQUETAS.get(tabla, f"CAST({col} AS NVARCHAR(20))")
        _, filas = self.consultar(f"SELECT {col}, {expr} FROM {tabla} {where} ORDER BY {col}", params)
        return [f"{f[0]} - {f[1]}" for f in filas]


# ----------------------------------------------------------------------
# Componentes reutilizables
# ----------------------------------------------------------------------
def crear_tabla_resultados(padre):
    marco = ttk.Frame(padre)
    arbol = ttk.Treeview(marco, show="headings", selectmode="browse")
    vsb = ttk.Scrollbar(marco, orient="vertical", command=arbol.yview)
    hsb = ttk.Scrollbar(marco, orient="horizontal", command=arbol.xview)
    arbol.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    arbol.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    marco.rowconfigure(0, weight=1)
    marco.columnconfigure(0, weight=1)
    return marco, arbol


def formatear(valor):
    if valor is None:
        return ""
    if isinstance(valor, dt.datetime):
        return valor.strftime("%Y-%m-%d %H:%M")
    return str(valor)


def mostrar_filas(arbol, columnas, filas, datos=None):
    arbol.delete(*arbol.get_children())
    arbol["columns"] = columnas
    for i, c in enumerate(columnas):
        ancho = max(len(c), *(len(formatear(f[i])) for f in filas[:60])) if filas else len(c)
        arbol.heading(c, text=c)
        arbol.column(c, width=max(80, min(280, ancho * 9 + 16)), stretch=False, anchor="w")
    for f in filas:
        valores = [formatear(v) for v in f]
        iid = arbol.insert("", "end", values=valores)
        if datos is not None:
            datos[iid] = valores


def poner_combo(var, combo, valor):
    for opcion in combo["values"]:
        if opcion.split(" - ")[0] == valor:
            var.set(opcion)
            return
    var.set(valor)


# ----------------------------------------------------------------------
# Pestaña 1: CRUD genérico sobre cualquier tabla
# ----------------------------------------------------------------------
class PanelCRUD(ttk.Frame):
    def __init__(self, master, bd):
        super().__init__(master)
        self.bd = bd
        self.tabla = None
        self.cols = []
        self.vars = {}
        self.combos = {}
        self.fks = {}
        self.filas = []
        self.datos = {}

        arriba = ttk.Frame(self)
        arriba.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Label(arriba, text="Tabla:").pack(side="left")
        self.cb_tabla = ttk.Combobox(arriba, values=bd.tablas(), state="readonly", width=30)
        self.cb_tabla.pack(side="left", padx=6)
        self.cb_tabla.bind("<<ComboboxSelected>>", self.cambiar_tabla)
        ttk.Label(arriba, text="Buscar:").pack(side="left", padx=(24, 4))
        self.var_buscar = tk.StringVar()
        self.var_buscar.trace_add("write", lambda *_: self.filtrar())
        ttk.Entry(arriba, textvariable=self.var_buscar, width=28).pack(side="left")
        self.lbl_total = ttk.Label(arriba, text="")
        self.lbl_total.pack(side="right")

        marco, self.arbol = crear_tabla_resultados(self)
        marco.pack(fill="both", expand=True, padx=10, pady=4)
        self.arbol.bind("<<TreeviewSelect>>", self.seleccionar)

        self.formulario = ttk.LabelFrame(self, text="Datos del registro (los campos con * son obligatorios)")
        self.formulario.pack(fill="x", padx=10, pady=4)

        botones = ttk.Frame(self)
        botones.pack(fill="x", padx=10, pady=(4, 10))
        ttk.Button(botones, text="Registrar nuevo", style="Acento.TButton", command=self.registrar).pack(side="left", padx=4)
        ttk.Button(botones, text="Actualizar", command=self.actualizar).pack(side="left", padx=4)
        ttk.Button(botones, text="Eliminar", command=self.eliminar).pack(side="left", padx=4)
        ttk.Button(botones, text="Limpiar formulario", command=self.nuevo).pack(side="left", padx=4)
        ttk.Button(botones, text="Refrescar", command=self.recargar).pack(side="right", padx=4)

        self.cb_tabla.current(0)
        self.cambiar_tabla()

    # -- construcción del formulario según los metadatos de la tabla --
    def cambiar_tabla(self, _evento=None):
        self.tabla = self.cb_tabla.get()
        self.cols = self.bd.columnas(self.tabla)
        self.fks = self.bd.fks(self.tabla)
        listas = self.bd.listas_check(self.tabla)
        for w in self.formulario.winfo_children():
            w.destroy()
        self.vars, self.combos = {}, {}
        por_fila = 3
        for i, c in enumerate(self.cols):
            fila, bloque = divmod(i, por_fila)
            nombre = c["nombre"]
            obligatorio = (not c["nulo"]) and (not c["identity"]) and (not c["default"])
            pista = {"date": " (AAAA-MM-DD)", "time": " (HH:MM:SS)", "datetime2": " (AAAA-MM-DD HH:MM)"}.get(c["tipo"], "")
            ttk.Label(self.formulario, text=f"{nombre}{'*' if obligatorio else ''}{pista}").grid(
                row=fila, column=bloque * 2, sticky="e", padx=(8, 4), pady=3)
            var = tk.StringVar()
            self.vars[nombre] = var
            if c["identity"]:
                w = ttk.Entry(self.formulario, textvariable=var, width=30, state="readonly")
            elif nombre in self.fks:
                tabla_ref, col_ref = self.fks[nombre]
                valores = ([""] if c["nulo"] else []) + self.bd.opciones(tabla_ref, col=col_ref)
                w = ttk.Combobox(self.formulario, textvariable=var, values=valores, state="readonly", width=40)
                self.combos[nombre] = w
            elif nombre in listas:
                w = ttk.Combobox(self.formulario, textvariable=var, values=listas[nombre], state="readonly", width=28)
                self.combos[nombre] = w
            else:
                w = ttk.Entry(self.formulario, textvariable=var, width=30)
            w.grid(row=fila, column=bloque * 2 + 1, sticky="w", padx=(0, 12), pady=3)
        self.var_buscar.set("")
        self.refrescar()

    def recargar(self):
        """Vuelve a leer opciones de llaves foráneas y filas (por cambios en otras pestañas)."""
        actual = self.tabla
        self.bd._cols.clear()
        self.cb_tabla.set(actual)
        self.cambiar_tabla()

    # -- datos --
    def refrescar(self):
        pk = self.bd.pk(self.tabla)
        _, self.filas = self.bd.consultar(f"SELECT * FROM {self.tabla} ORDER BY {pk}")
        self.filtrar()

    def filtrar(self):
        if not self.tabla:
            return
        q = self.var_buscar.get().strip().lower()
        columnas = [c["nombre"] for c in self.cols]
        visibles = []
        for f in self.filas:
            texto = " ".join(formatear(v) for v in f).lower()
            if not q or q in texto:
                visibles.append(f)
        self.datos = {}
        mostrar_filas(self.arbol, columnas, visibles, self.datos)
        self.lbl_total.config(text=f"{len(visibles)} de {len(self.filas)} registros")

    def seleccionar(self, _evento=None):
        sel = self.arbol.selection()
        if not sel:
            return
        valores = self.datos.get(sel[0], [])
        for c, v in zip(self.cols, valores):
            var = self.vars[c["nombre"]]
            if c["nombre"] in self.combos:
                poner_combo(var, self.combos[c["nombre"]], v)
            else:
                var.set(v)

    def nuevo(self):
        for v in self.vars.values():
            v.set("")
        self.arbol.selection_remove(self.arbol.selection())

    def valor(self, col):
        texto = self.vars[col["nombre"]].get().strip()
        if texto == "":
            return None
        if col["nombre"] in self.fks:
            return texto.split(" - ")[0]
        return texto

    # -- operaciones CRUD --
    def _correr(self, sql, params, mensaje):
        try:
            self.bd.ejecutar(sql, params)
        except pyodbc.Error as e:
            messagebox.showerror("No se pudo completar la operación", traducir_error(e))
            return
        self.refrescar()
        self.nuevo()
        messagebox.showinfo("Listo", mensaje)

    def registrar(self):
        pares = [(c["nombre"], self.valor(c)) for c in self.cols if not c["identity"]]
        pares = [(n, v) for n, v in pares if v is not None]
        if not pares:
            messagebox.showwarning("Faltan datos", "Completa el formulario para registrar.")
            return
        sql = (f"INSERT INTO {self.tabla} ({', '.join(n for n, _ in pares)}) "
               f"VALUES ({', '.join('?' for _ in pares)})")
        self._correr(sql, [v for _, v in pares], "Registro creado correctamente.")

    def actualizar(self):
        pk = self.bd.pk(self.tabla)
        col_pk = next(c for c in self.cols if c["nombre"] == pk)
        id_actual = self.vars[pk].get().strip()
        if not id_actual:
            messagebox.showwarning("Selecciona un registro", "Elige una fila de la tabla para actualizarla.")
            return
        editables = [c for c in self.cols if not c["pk"] and not c["identity"]]
        sets = ", ".join(f"{c['nombre']} = ?" for c in editables)
        params = [self.valor(c) for c in editables] + [id_actual]
        self._correr(f"UPDATE {self.tabla} SET {sets} WHERE {col_pk['nombre']} = ?", params,
                     "Registro actualizado correctamente.")

    def eliminar(self):
        pk = self.bd.pk(self.tabla)
        id_actual = self.vars[pk].get().strip()
        if not id_actual:
            messagebox.showwarning("Selecciona un registro", "Elige una fila de la tabla para eliminarla.")
            return
        if not messagebox.askyesno("Confirmar", f"¿Eliminar el registro {id_actual} de {self.tabla}?"):
            return
        self._correr(f"DELETE FROM {self.tabla} WHERE {pk} = ?", [id_actual], "Registro eliminado.")


# ----------------------------------------------------------------------
# Pestaña 2: operaciones del negocio (procedimientos almacenados)
# ----------------------------------------------------------------------
class Formulario(ttk.LabelFrame):
    """Formulario que ejecuta un procedimiento almacenado.
    campos: (clave, etiqueta, tipo, fuente, recarga_hijo)
      tipo: 'combo' | 'texto'
      fuente: función(formulario) -> lista de opciones
      recarga_hijo: clave del campo que depende de este combo"""

    def __init__(self, master, bd, titulo, ayuda, campos, procedimiento, mensaje_exito, al_exito):
        super().__init__(master, text=titulo)
        self.bd, self.campos, self.proc, self.mensaje_exito = bd, campos, procedimiento, mensaje_exito
        self.al_exito = al_exito
        self.vars, self.widgets = {}, {}
        ttk.Label(self, text=ayuda, foreground="#555", wraplength=420, justify="left").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(4, 6))
        for i, (clave, etiqueta, tipo, fuente, hijo) in enumerate(campos, start=1):
            ttk.Label(self, text=etiqueta).grid(row=i, column=0, sticky="e", padx=(8, 4), pady=2)
            var = tk.StringVar()
            self.vars[clave] = var
            if tipo == "combo":
                w = ttk.Combobox(self, textvariable=var, state="readonly", width=46)
                if hijo:
                    w.bind("<<ComboboxSelected>>", lambda _e, h=hijo: self.recargar_campo(h))
            else:
                w = ttk.Entry(self, textvariable=var, width=48)
            w.grid(row=i, column=1, sticky="w", padx=(0, 8), pady=2)
            self.widgets[clave] = w
        ttk.Button(self, text="Ejecutar", style="Acento.TButton", command=self.enviar).grid(
            row=len(campos) + 1, column=1, sticky="e", padx=8, pady=8)
        self.recargar()

    def recargar_campo(self, clave):
        for c in self.campos:
            if c[0] == clave and c[3]:
                self.vars[clave].set("")
                self.widgets[clave]["values"] = c[3](self)

    def recargar(self):
        for clave, _etq, tipo, fuente, _h in self.campos:
            if tipo == "combo" and fuente:
                self.widgets[clave]["values"] = fuente(self)

    def valor(self, clave):
        texto = self.vars[clave].get().strip()
        if texto == "":
            return None
        tipo = next(c[2] for c in self.campos if c[0] == clave)
        return texto.split(" - ")[0] if tipo == "combo" else texto

    def enviar(self):
        params = [self.valor(c[0]) for c in self.campos]
        if any(p is None for p in params):
            messagebox.showwarning("Faltan datos", "Completa todos los campos del formulario.")
            return
        marcas = ", ".join("?" for _ in params)
        try:
            cols, filas = self.bd.consultar(f"EXEC {self.proc} {marcas}", params)
        except pyodbc.Error as e:
            messagebox.showerror("No se pudo completar la operación", traducir_error(e))
            return
        resultado = dict(zip(cols, filas[0])) if filas else {}
        messagebox.showinfo("Operación exitosa", self.mensaje_exito(resultado))
        for v in self.vars.values():
            v.set("")
        self.al_exito()


class PanelOperaciones(ttk.Frame):
    def __init__(self, master, bd, al_cambiar):
        super().__init__(master)
        self.bd = bd
        self.al_cambiar = al_cambiar
        o = bd.opciones
        cuadricula = ttk.Frame(self)
        cuadricula.pack(fill="both", expand=True, padx=10, pady=10)
        cuadricula.columnconfigure(0, weight=1)
        cuadricula.columnconfigure(1, weight=1)

        def F(*args):
            return Formulario(cuadricula, bd, *args, al_cambiar)

        def solicitudes(_f):
            return o("SOLICITUD", "WHERE estado_solicitud IN (N'Pendiente', N'Aprobada') "
                                  "AND id_solicitud NOT IN (SELECT id_solicitud FROM RESERVA)")

        def condiciones(_f): return o("CONDICION_CONTRATACION")
        def empleados(_f): return o("EMPLEADO", "WHERE estado_empleado = N'Activo'")
        def reservas_abiertas(_f):
            return o("RESERVA", "WHERE estado_reserva IN (N'Pendiente', N'Confirmada', N'En curso')")
        def espacios(_f): return o("ESPACIO", "WHERE estado_espacio NOT IN (N'Mantenimiento', N'Inactivo')")
        def tarifas(f):
            esp = f.valor("espacio")
            return o("TARIFA_ESPACIO", "WHERE id_espacio = ? AND estado_tarifa <> N'Inactiva'", (esp,)) if esp else []
        def metodos(_f): return o("METODO_PAGO")
        def detalles(_f): return o("DETALLE_RESERVA", "WHERE estado_detalle IN (N'Reservado', N'En uso')")
        def personas(_f): return o("PERSONA_AUTORIZADA")

        self.formularios = [
            F("1. Crear reserva desde una solicitud",
                       "Confirma una solicitud y genera su reserva con la condición de contratación elegida.",
                       [("solicitud", "Solicitud", "combo", solicitudes, None),
                        ("condicion", "Condición de contratación", "combo", condiciones, None),
                        ("empleado", "Empleado responsable", "combo", empleados, None)],
                       "sp_crear_reserva", lambda r: f"Reserva #{r.get('id_reserva')} creada y confirmada."),
            F("2. Agregar un espacio a una reserva",
                       "Calcula cantidad, precio y subtotal. Valida tarifa, vigencia y traslapes de horario.",
                       [("reserva", "Reserva", "combo", reservas_abiertas, None),
                        ("espacio", "Espacio", "combo", espacios, "tarifa"),
                        ("tarifa", "Tarifa del espacio", "combo", tarifas, None),
                        ("inicio", "Inicio (AAAA-MM-DD HH:MM)", "texto", None, None),
                        ("fin", "Fin (AAAA-MM-DD HH:MM)", "texto", None, None),
                        ("empleado", "Empleado responsable", "combo", empleados, None)],
                       "sp_agregar_detalle_reserva",
                       lambda r: f"Espacio agregado (detalle #{r.get('id_detalle_reserva')}). El total de la reserva se recalculó."),
            F("3. Registrar un pago",
                       "No permite pagar más que el saldo pendiente de la reserva.",
                       [("reserva", "Reserva", "combo", reservas_abiertas, None),
                        ("metodo", "Método de pago", "combo", metodos, None),
                        ("monto", "Monto ($)", "texto", None, None),
                        ("comprobante", "N.º de comprobante", "texto", None, None),
                        ("empleado", "Empleado responsable", "combo", empleados, None)],
                       "sp_registrar_pago",
                       lambda r: f"Pago #{r.get('id_pago')} registrado. Saldo restante: ${r.get('saldo_restante')}"),
            F("4. Cancelar una reserva",
                       "Libera los espacios y calcula la penalidad según la condición contratada.",
                       [("reserva", "Reserva", "combo", reservas_abiertas, None),
                        ("motivo", "Motivo de la cancelación", "texto", None, None),
                        ("empleado", "Empleado responsable", "combo", empleados, None)],
                       "sp_cancelar_reserva",
                       lambda r: f"Reserva #{r.get('id_reserva')} cancelada. Penalidad aplicable: ${r.get('penalidad_aplicable')}"),
            F("5. Registrar acceso de una persona",
                       "Solo pueden ingresar personas autorizadas en la reserva del espacio.",
                       [("detalle", "Espacio reservado (detalle)", "combo", detalles, None),
                        ("persona", "Persona autorizada", "combo", personas, None)],
                       "sp_registrar_acceso", lambda r: f"Acceso #{r.get('id_acceso')} registrado."),
        ]
        for i, f in enumerate(self.formularios):
            f.grid(row=i // 2, column=i % 2, sticky="nsew", padx=6, pady=6)

    def recargar(self):
        for f in self.formularios:
            f.recargar()


# ----------------------------------------------------------------------
# Pestaña 3: consultas
# ----------------------------------------------------------------------
class PanelConsultas(ttk.Frame):
    def __init__(self, master, bd):
        super().__init__(master)
        self.bd = bd
        arriba = ttk.Frame(self)
        arriba.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Label(arriba, text="Consulta:").pack(side="left")
        self.cb = ttk.Combobox(arriba, values=[c[0] for c in CONSULTAS], state="readonly", width=52)
        self.cb.pack(side="left", padx=6)
        self.cb.current(0)
        self.cb.bind("<<ComboboxSelected>>", self.cambiar)
        ttk.Button(arriba, text="Ejecutar consulta", style="Acento.TButton", command=self.ejecutar).pack(side="left", padx=8)

        self.lbl_desc = ttk.Label(self, text="", foreground="#444", wraplength=1000, justify="left")
        self.lbl_desc.pack(fill="x", padx=12, pady=2)

        self.params = ttk.LabelFrame(self, text="Parámetros")
        manana = dt.datetime.now().replace(hour=9, minute=0, second=0, microsecond=0) + dt.timedelta(days=1)
        self.v_ini = tk.StringVar(value=manana.strftime("%Y-%m-%d %H:%M"))
        self.v_fin = tk.StringVar(value=(manana + dt.timedelta(hours=4)).strftime("%Y-%m-%d %H:%M"))
        self.v_sede = tk.StringVar()
        self.v_tipo = tk.StringVar()
        ttk.Label(self.params, text="Inicio (AAAA-MM-DD HH:MM)").grid(row=0, column=0, padx=6, pady=4)
        ttk.Entry(self.params, textvariable=self.v_ini, width=20).grid(row=0, column=1, padx=6)
        ttk.Label(self.params, text="Fin (AAAA-MM-DD HH:MM)").grid(row=0, column=2, padx=6)
        ttk.Entry(self.params, textvariable=self.v_fin, width=20).grid(row=0, column=3, padx=6)
        ttk.Label(self.params, text="Sede (opcional)").grid(row=1, column=0, padx=6, pady=4)
        self.cb_sede = ttk.Combobox(self.params, textvariable=self.v_sede, state="readonly", width=34)
        self.cb_sede.grid(row=1, column=1, columnspan=1, padx=6)
        ttk.Label(self.params, text="Tipo de espacio (opcional)").grid(row=1, column=2, padx=6)
        self.cb_tipo = ttk.Combobox(self.params, textvariable=self.v_tipo, state="readonly", width=34)
        self.cb_tipo.grid(row=1, column=3, padx=6)

        marco, self.arbol = crear_tabla_resultados(self)
        marco.pack(fill="both", expand=True, padx=10, pady=8)
        self.lbl_total = ttk.Label(self, text="")
        self.lbl_total.pack(anchor="e", padx=12, pady=(0, 8))
        self.recargar()
        self.cambiar()

    def recargar(self):
        self.cb_sede["values"] = [""] + self.bd.opciones("SEDE")
        self.cb_tipo["values"] = [""] + self.bd.opciones("TIPO_ESPACIO")

    def actual(self):
        return CONSULTAS[self.cb.current()]

    def cambiar(self, _e=None):
        nombre, descripcion, _sql, modo = self.actual()
        self.lbl_desc.config(text=f"Pregunta de negocio: {descripcion}")
        if modo == "disponibilidad":
            self.params.pack(fill="x", padx=10, pady=4, before=self.arbol.master)
        else:
            self.params.pack_forget()

    def ejecutar(self):
        _n, _d, sql, modo = self.actual()
        params = ()
        if modo == "disponibilidad":
            def id_de(texto):
                return texto.split(" - ")[0] if texto else None
            params = (self.v_ini.get().strip(), self.v_fin.get().strip(),
                      id_de(self.v_sede.get()), id_de(self.v_tipo.get()))
        try:
            columnas, filas = self.bd.consultar(sql, params)
        except pyodbc.Error as e:
            messagebox.showerror("No se pudo ejecutar la consulta", traducir_error(e))
            return
        mostrar_filas(self.arbol, columnas, filas)
        self.lbl_total.config(text=f"{len(filas)} resultado(s)")


# ----------------------------------------------------------------------
# Ventana principal
# ----------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self.title("Coworking | Gestión de espacios compartidos - Grupo 8")
        self.geometry("1280x800")
        self.minsize(1100, 700)
        self.configure(bg=COLOR_FONDO)
        self._estilos()
        self.bd = None
        if not self._login():
            self.destroy()
            sys.exit(0)

        cabecera = tk.Frame(self, bg=COLOR_PRIMARIO)
        cabecera.pack(fill="x")
        tk.Label(cabecera, text="Plataforma de gestión de espacios de coworking", bg=COLOR_PRIMARIO, fg="white",
                 font=("Segoe UI", 16, "bold")).pack(side="left", padx=16, pady=10)
        tk.Label(cabecera, text=f"Base de datos: {DB_NAME}", bg=COLOR_PRIMARIO, fg="#cbd5e1",
                 font=("Segoe UI", 10)).pack(side="right", padx=16)
        tk.Frame(self, bg=COLOR_ACENTO, height=3).pack(fill="x")

        self.libro = ttk.Notebook(self)
        self.libro.pack(fill="both", expand=True)
        self.crud = PanelCRUD(self.libro, self.bd)
        self.operaciones = PanelOperaciones(self.libro, self.bd, self.refrescar_todo)
        self.consultas = PanelConsultas(self.libro, self.bd)
        self.libro.add(self.crud, text="  Gestión de datos (CRUD)  ")
        self.libro.add(self.operaciones, text="  Reservas y pagos  ")
        self.libro.add(self.consultas, text="  Consultas del negocio  ")
        self.libro.bind("<<NotebookTabChanged>>", lambda _e: self.refrescar_todo())
        self.deiconify()

    def refrescar_todo(self):
        self.operaciones.recargar()
        self.consultas.recargar()
        if self.libro.index(self.libro.select()) == 0:
            self.crud.recargar()

    def _estilos(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TFrame", background=COLOR_FONDO)
        s.configure("TLabel", background=COLOR_FONDO, font=("Segoe UI", 10))
        s.configure("TLabelframe", background=COLOR_FONDO)
        s.configure("TLabelframe.Label", background=COLOR_FONDO, foreground=COLOR_PRIMARIO, font=("Segoe UI", 10, "bold"))
        s.configure("TNotebook.Tab", padding=(10, 6), font=("Segoe UI", 10, "bold"))
        s.configure("Treeview", rowheight=24, font=("Segoe UI", 9))
        s.configure("Treeview.Heading", background=COLOR_PRIMARIO, foreground="white", font=("Segoe UI", 9, "bold"))
        s.map("Treeview.Heading", background=[("active", COLOR_PRIMARIO)])
        s.configure("TButton", padding=(10, 5), font=("Segoe UI", 10))
        s.configure("Acento.TButton", background=COLOR_ACENTO, foreground="white", font=("Segoe UI", 10, "bold"))
        s.map("Acento.TButton", background=[("active", "#d97a1c")])

    def _login(self):
        dlg = tk.Toplevel(self)
        dlg.title("Conexión a SQL Server")
        dlg.configure(bg=COLOR_FONDO)
        dlg.resizable(False, False)
        dlg.grab_set()
        marco = ttk.Frame(dlg, padding=18)
        marco.pack()
        ttk.Label(marco, text="Conectar a SQL Server", font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=2, pady=(0, 10))
        v_srv = tk.StringVar(value=os.environ.get("COWORKING_SERVER", r"localhost"))
        v_usr = tk.StringVar()
        v_pwd = tk.StringVar()
        ttk.Label(marco, text="Servidor").grid(row=1, column=0, sticky="e", pady=4, padx=4)
        ttk.Entry(marco, textvariable=v_srv, width=34).grid(row=1, column=1, pady=4)
        ttk.Label(marco, text="Usuario SQL").grid(row=2, column=0, sticky="e", pady=4, padx=4)
        ttk.Entry(marco, textvariable=v_usr, width=34).grid(row=2, column=1, pady=4)
        ttk.Label(marco, text="Contraseña").grid(row=3, column=0, sticky="e", pady=4, padx=4)
        ttk.Entry(marco, textvariable=v_pwd, show="*", width=34).grid(row=3, column=1, pady=4)
        ttk.Label(marco, text="Si dejas el usuario vacío se usa la autenticación de Windows.\n"
                              r"Ejemplos de servidor: localhost  |  localhost\SQLEXPRESS  |  .\SQLEXPRESS",
                  foreground="#555").grid(row=4, column=0, columnspan=2, pady=(6, 10))
        resultado = {"ok": False}

        def intentar(_e=None):
            try:
                conexion = conectar(v_srv.get().strip(), v_usr.get().strip(), v_pwd.get())
            except Exception as e:  # noqa: BLE001
                texto = limpiar_mensaje(e) if isinstance(e, pyodbc.Error) else str(e)
                messagebox.showerror("No se pudo conectar",
                                     f"{texto}\n\nVerifica que SQL Server esté activo y que ya ejecutaste el script "
                                     f"01_script_coworking.sql (base {DB_NAME}).", parent=dlg)
                return
            self.bd = BD(conexion)
            resultado["ok"] = True
            dlg.destroy()

        ttk.Button(marco, text="Conectar", style="Acento.TButton", command=intentar).grid(row=5, column=1, sticky="e")
        dlg.bind("<Return>", intentar)
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        dlg.update_idletasks()
        x = (dlg.winfo_screenwidth() - dlg.winfo_width()) // 2
        y = (dlg.winfo_screenheight() - dlg.winfo_height()) // 3
        dlg.geometry(f"+{x}+{y}")
        self.wait_window(dlg)
        return resultado["ok"]


if __name__ == "__main__":
    App().mainloop()
