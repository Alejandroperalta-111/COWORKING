
const $ = s => document.querySelector(s);

const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;"
}[c]));

const PISTAS = {
    date: " (AAAA-MM-DD)",
    time: " (HH:MM:SS)",
    datetime2: " (AAAA-MM-DD HH:MM)"
};

// =====================================================
// CONEXIÓN CON FLASK
// =====================================================

async function api(url, metodo = "GET", cuerpo) {
    const r = await fetch(url, {
        method: metodo,
        headers: {
            "Content-Type": "application/json"
        },
        body: cuerpo !== undefined && cuerpo !== null
            ? JSON.stringify(cuerpo)
            : undefined
    });

    let d;

    try {
        d = await r.json();
    } catch {
        throw new Error("El servidor devolvió una respuesta no válida.");
    }

    if (!r.ok) {
        throw new Error(d.error || "Error desconocido");
    }

    return d;
}

// =====================================================
// NOTIFICACIONES
// =====================================================

function aviso(titulo, texto, error = false) {
    const contenedor = $("#toasts");

    if (!contenedor) {
        alert(`${titulo}\n${texto}`);
        return;
    }

    const t = document.createElement("div");

    t.className = "toast" + (error ? " err" : "");
    t.innerHTML = `<b>${esc(titulo)}</b>${esc(texto)}`;

    contenedor.appendChild(t);

    setTimeout(() => t.remove(), error ? 9000 : 4500);
}

const ok = (m, t = "Listo") => aviso(t, m);

const fallo = (e, t = "No se pudo completar la operación") =>
    aviso(t, e.message || String(e), true);

// =====================================================
// TABLAS
// =====================================================

function dibujar(cont, columnas, filas, alClic) {
    if (!columnas.length) {
        cont.innerHTML = '<div class="vacio">Sin datos</div>';
        return;
    }

    cont.innerHTML = `
        <table>
            <thead>
                <tr>
                    ${columnas.map(c => `<th>${esc(c)}</th>`).join("")}
                </tr>
            </thead>

            <tbody>
                ${filas.map((f, i) => `
                    <tr data-i="${i}">
                        ${f.map(v => `
                            <td title="${esc(v)}">${esc(v)}</td>
                        `).join("")}
                    </tr>
                `).join("")}
            </tbody>
        </table>

        ${filas.length ? "" : '<div class="vacio">Sin resultados</div>'}
    `;

    if (alClic) {
        cont.querySelectorAll("tbody tr").forEach(tr => {
            tr.onclick = () => {
                cont.querySelectorAll("tr.sel").forEach(x =>
                    x.classList.remove("sel")
                );

                tr.classList.add("sel");

                alClic(filas[Number(tr.dataset.i)]);
            };
        });
    }
}

function campo(etiqueta, elemento) {
    const d = document.createElement("div");

    const label = document.createElement("label");
    label.textContent = etiqueta;

    d.appendChild(label);
    d.appendChild(elemento);

    return d;
}

// =====================================================
// COMBOS Y LLAVES FORÁNEAS
// =====================================================

function combo(opciones, esFk = false) {
    const s = document.createElement("select");

    s.appendChild(
        new Option("Selecciona una opción", "")
    );

    (opciones || []).filter(o => o !== "").forEach(o => {
        const texto = String(o);

        if (esFk && texto.includes(" - ")) {
            const [id, ...partes] = texto.split(" - ");
            const nombre = partes.join(" - ");

            s.appendChild(
                new Option(nombre, id)
            );
        } else {
            s.appendChild(
                new Option(texto, texto)
            );
        }
    });

    return s;
}

// =====================================================
// CONEXIÓN A SQL SERVER
// =====================================================

async function conectar() {
    try {
        const d = await api("/api/login", "POST", {
            servidor: $("#l-srv").value,
            usuario: $("#l-usr").value,
            clave: $("#l-pwd").value
        });

        $("#login").classList.add("hidden");

        $("#base").textContent = "Base de datos: " + d.base;

        $("#c-tabla").innerHTML = d.tablas
            .map(t => `<option value="${esc(t)}">${esc(t)}</option>`)
            .join("");

        await cargarTabla();

    } catch (e) {
        fallo(e, "No se pudo conectar");
    }
}

$("#l-ok").onclick = conectar;

document.addEventListener("keydown", e => {
    if (
        e.key === "Enter" &&
        $("#login") &&
        !$("#login").classList.contains("hidden")
    ) {
        conectar();
    }
});

// =====================================================
// NAVEGACIÓN ENTRE SECCIONES
// =====================================================

function mostrarSeccion(nombre) {
    const secciones = ["crud", "ops", "con"];

    secciones.forEach(nombreSeccion => {
        const seccion = document.getElementById(
            "tab-" + nombreSeccion
        );

        if (seccion) {
            seccion.classList.toggle(
                "hidden",
                nombreSeccion !== nombre
            );
        }
    });

    document.querySelectorAll("nav button[data-tab]").forEach(b => {
        b.classList.toggle(
            "on",
            b.dataset.tab === nombre
        );
    });

    const submenu = $("#submenu-ops");

    if (submenu) {
        submenu.classList.toggle(
            "visible",
            nombre === "ops"
        );
    }

    if (nombre === "crud") {
        cargarTabla();
    }

    if (nombre === "ops") {
        cargarOps();
    }

    if (nombre === "con") {
        cargarConsultas();
    }
}

document.querySelectorAll("nav button[data-tab]").forEach(b => {
    b.addEventListener("click", () => {
        mostrarSeccion(b.dataset.tab);
    });
});

// =====================================================
// GESTIÓN CRUD
// =====================================================

let M = null;
let entradas = {};

async function cargarTabla() {
    const t = $("#c-tabla").value;

    if (!t) return;

    try {
        M = await api("/api/tabla/" + encodeURIComponent(t));
    } catch (e) {
        return fallo(e);
    }

    const f = $("#c-form");

    f.innerHTML = "";
    entradas = {};

    M.columnas.forEach(c => {
        let el;

        if (c.identity) {
            el = document.createElement("input");
            el.readOnly = true;

        } else if (c.opciones) {
            el = combo(c.opciones, Boolean(c.fk));

        } else {
            el = document.createElement("input");

            if (c.tipo === "date") {
                el.type = "date";

            } else if (c.tipo === "time") {
                el.type = "time";

            } else if (
                ["datetime2", "datetime", "datetimeoffset"].includes(c.tipo)
            ) {
                el.type = "datetime-local";
            }
        }

        entradas[c.nombre] = el;

        const etiqueta =
            c.fk && c.nombre === "id_usuario"
                ? "Usuario" + (c.obligatorio ? " *" : "")
                : c.nombre + (c.obligatorio ? " *" : "") +
                  (PISTAS[c.tipo] || "");

        f.appendChild(campo(etiqueta, el));

        // ID del usuario en un campo separado
        if (c.fk && c.nombre === "id_usuario") {
            const idVisible = document.createElement("input");

            idVisible.type = "text";
            idVisible.readOnly = true;
            idVisible.className = "campo-lectura";
            idVisible.placeholder = "ID automático";
            idVisible.setAttribute("aria-label", "id_usuario");

            entradas["id_usuario__id_visible"] = idVisible;

            el.addEventListener("change", () => {
                idVisible.value = el.value;
            });

            f.appendChild(
                campo("id_usuario", idVisible)
            );
        }
    });

    pintar();
}

// =====================================================
// BUSCADOR GENERAL
// =====================================================

// Quita tildes y normaliza el texto
function normalizar(valor) {
    return String(valor ?? "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLocaleLowerCase("es")
        .trim();
}

// Comprueba si el texto comienza por la búsqueda.
// También revisa el inicio de cada palabra.
function coincideInicio(valor, busqueda) {
    const texto = normalizar(valor);
    const termino = normalizar(busqueda);

    if (!termino) return true;

    if (texto.startsWith(termino)) {
        return true;
    }

    const palabras = texto.split(/\s+/);

    return palabras.some(palabra =>
        palabra.startsWith(termino)
    );
}

// Filtra registros de acuerdo con todos sus campos
function filtrarRegistros(filas, busqueda) {
    if (!busqueda) return filas;

    return filas.filter(fila =>
        fila.some(valor =>
            coincideInicio(valor, busqueda)
        )
    );
}

// =====================================================
// MOSTRAR TABLA FILTRADA
// =====================================================

function pintar() {
    if (!M) return;

    const q = $("#c-buscar").value;

    const vis = filtrarRegistros(M.filas, q);

    dibujar(
        $("#c-grid"),
        M.columnas.map(c => c.nombre),
        vis,
        seleccionar
    );

    $("#c-total").textContent =
        `${vis.length} de ${M.filas.length} registros`;
}

// =====================================================
// SELECCIONAR REGISTRO
// =====================================================

function seleccionar(fila) {
    M.columnas.forEach((c, i) => {
        const el = entradas[c.nombre];
        const v = fila[i];

        if (!el) return;

        el.value = v ?? "";

        if (c.fk && c.nombre === "id_usuario") {
            const idVisible = entradas["id_usuario__id_visible"];

            if (idVisible) {
                idVisible.value = v ?? "";
            }
        }
    });
}

// =====================================================
// LIMPIAR FORMULARIO
// =====================================================

function limpiar() {
    Object.values(entradas).forEach(e => {
        e.value = "";
    });

    document.querySelectorAll("#c-grid tr.sel").forEach(x =>
        x.classList.remove("sel")
    );
}

// =====================================================
// OBTENER DATOS DEL FORMULARIO
// =====================================================

function datosForm() {
    const d = {};

    M.columnas.forEach(c => {
        // Se envía el valor real del combo.
        // Para las llaves foráneas es solamente el ID.
        d[c.nombre] = entradas[c.nombre].value.trim();
    });

    return d;
}

// =====================================================
// OPERACIONES CRUD
// =====================================================

async function crud(metodo, url, cuerpo, confirmar) {
    if (confirmar && !confirm(confirmar)) {
        return;
    }

    try {
        const r = await api(url, metodo, cuerpo);

        ok(r.mensaje);

        await cargarTabla();
        limpiar();

    } catch (e) {
        fallo(e);
    }
}

// =====================================================
// EVENTOS CRUD
// =====================================================

$("#c-tabla").onchange = () => {
    $("#c-buscar").value = "";
    cargarTabla();
};

$("#c-buscar").oninput = pintar;

$("#b-ref").onclick = cargarTabla;

$("#b-lim").onclick = limpiar;

// REGISTRAR
$("#b-reg").onclick = () => {
    if (!M) return;

    crud(
        "POST",
        "/api/tabla/" + encodeURIComponent($("#c-tabla").value),
        datosForm()
    );
};

// ACTUALIZAR
$("#b-act").onclick = () => {
    if (!M) return;

    const id = entradas[M.pk]?.value.trim();

    if (!id) {
        return aviso(
            "Selecciona un registro",
            "Elige una fila de la tabla para actualizarla.",
            true
        );
    }

    crud(
        "PUT",
        `/api/tabla/${encodeURIComponent($("#c-tabla").value)}/${encodeURIComponent(id)}`,
        datosForm()
    );
};

// ELIMINAR
$("#b-del").onclick = () => {
    if (!M) return;

    const id = entradas[M.pk]?.value.trim();

    if (!id) {
        return aviso(
            "Selecciona un registro",
            "Elige una fila de la tabla para eliminarla.",
            true
        );
    }

    crud(
        "DELETE",
        `/api/tabla/${encodeURIComponent($("#c-tabla").value)}/${encodeURIComponent(id)}`,
        null,
        `¿Eliminar el registro ${id} de ${$("#c-tabla").value}?`
    );
};

// =====================================================
// RESERVAS Y PAGOS
// =====================================================

let OPS_DEFS = [];
let OP_SELECCIONADA = 0;

function tipoCampoOperacion(c) {
    const clave = String(c.clave || "").toLowerCase();
    const etiqueta = String(c.etiqueta || "").toLowerCase();
    const nombre = clave + " " + etiqueta;

    if (c.tipo === "combo") return "combo";

    if (
        c.tipo === "date" ||
        (/fecha/.test(nombre) && !/hora|inicio|fin/.test(nombre))
    ) {
        return "date";
    }

    if (c.tipo === "time" || /hora/.test(nombre)) {
        return "time";
    }

    if (
        ["datetime2", "datetime", "datetime-local"].includes(c.tipo) ||
        /(fecha.*(inicio|fin)|\b(inicio|fin)\b.*fecha|fecha_hora|datetime)/.test(nombre)
    ) {
        return "datetime-local";
    }

    return "text";
}

// =====================================================
// MENÚ DE OPERACIONES
// =====================================================

function dibujarMenuOps() {
    const menu = $("#submenu-ops");

    menu.innerHTML = "";

    OPS_DEFS.forEach((d, i) => {
        const b = document.createElement("button");

        b.type = "button";
        b.textContent = d.titulo;

        b.className =
            i === OP_SELECCIONADA ? "selected" : "";

        b.onclick = () => {
            OP_SELECCIONADA = i;

            dibujarMenuOps();
            dibujarFormularioOperacion();
        };

        menu.appendChild(b);
    });
}

// =====================================================
// CARGAR OPERACIONES
// =====================================================

async function cargarOps() {
    try {
        OPS_DEFS = await api("/api/operaciones");

        if (!Array.isArray(OPS_DEFS)) {
            throw new Error("Formato de operaciones incorrecto.");
        }

        if (OP_SELECCIONADA >= OPS_DEFS.length) {
            OP_SELECCIONADA = 0;
        }

        dibujarMenuOps();
        dibujarFormularioOperacion();

    } catch (e) {
        fallo(e);
    }
}

// =====================================================
// FORMULARIOS DE OPERACIONES
// =====================================================

function dibujarFormularioOperacion() {
    const cont = $("#ops");

    cont.innerHTML = "";

    const d = OPS_DEFS[OP_SELECCIONADA];

    if (!d) {
        cont.innerHTML = `
            <div class="card">
                <div class="vacio">
                    No hay operaciones disponibles.
                </div>
            </div>
        `;

        return;
    }

    const card = document.createElement("div");
    card.className = "card";

    const h = document.createElement("h3");
    h.textContent = d.titulo;

    const p = document.createElement("p");
    p.className = "ayuda";
    p.textContent = d.ayuda || "Completa los datos de la operación.";

    card.appendChild(h);
    card.appendChild(p);

    const el = {};

    (d.campos || []).forEach(c => {
        const tipo = tipoCampoOperacion(c);

        if (tipo === "combo") {
            el[c.clave] = combo(c.opciones || [], true);
        } else {
            el[c.clave] = document.createElement("input");
            el[c.clave].type = tipo;

            if (tipo === "datetime-local") {
                el[c.clave].step = "60";
            }
        }

        if (c.requerido) {
            el[c.clave].required = true;
        }

        card.appendChild(
            campo(c.etiqueta || c.clave, el[c.clave])
        );
    });

    // Cargar tarifas según el espacio seleccionado
    if (el.espacio && el.tarifa) {
        el.espacio.onchange = async () => {
            try {
                const idEspacio = el.espacio.value;

                const tarifas = idEspacio
                    ? await api(
                        "/api/tarifas?espacio=" +
                        encodeURIComponent(idEspacio)
                    )
                    : [];

                el.tarifa.innerHTML =
                    combo(tarifas, true).innerHTML;

            } catch (e) {
                fallo(e, "No se pudieron cargar las tarifas");
            }
        };
    }

    const acciones = document.createElement("div");
    acciones.className = "acciones";

    const b = document.createElement("button");
    b.type = "button";
    b.className = "btn acc";
    b.textContent = "Ejecutar operación";

    b.onclick = async () => {
        const cuerpo = {};

        for (const [k, v] of Object.entries(el)) {
            if (v.required && !v.value) {
                aviso(
                    "Campo obligatorio",
                    "Completa: " + k,
                    true
                );

                v.focus();
                return;
            }

            cuerpo[k] = v.value;
        }

        try {
            const r = await api(
                "/api/operaciones/" + d.indice,
                "POST",
                cuerpo
            );

            ok(r.mensaje, "Operación exitosa");

            await cargarOps();

        } catch (e) {
            fallo(e);
        }
    };

    acciones.appendChild(b);
    card.appendChild(acciones);
    cont.appendChild(card);
}

// =====================================================
// CONSULTAS DEL NEGOCIO
// =====================================================

let CONS = [];

async function cargarConsultas() {
    try {
        const d = await api("/api/consultas");

        CONS = d.consultas;

        const prev = $("#q-sel").selectedIndex;

        $("#q-sel").innerHTML = CONS
            .map(c => `<option>${esc(c.nombre)}</option>`)
            .join("");

        $("#q-sel").selectedIndex =
            Math.max(prev, 0);

        $("#q-sede").innerHTML = d.sedes
            .map(s => `<option>${esc(s)}</option>`)
            .join("");

        $("#q-tipo").innerHTML = d.tipos
            .map(s => `<option>${esc(s)}</option>`)
            .join("");

        if (!$("#q-ini").value) {
            const m = new Date();

            m.setDate(m.getDate() + 1);
            m.setHours(9, 0, 0, 0);

            const formato = x =>
                `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}T${String(x.getHours()).padStart(2, "0")}:${String(x.getMinutes()).padStart(2, "0")}`;

            $("#q-ini").value = formato(m);

            m.setHours(13);

            $("#q-fin").value = formato(m);
        }

        cambiarConsulta();

    } catch (e) {
        fallo(e);
    }
}

// =====================================================
// CAMBIAR CONSULTA
// =====================================================

function cambiarConsulta() {
    const c = CONS[$("#q-sel").selectedIndex];

    if (!c) return;

    $("#q-desc").textContent =
        "Pregunta de negocio: " + c.descripcion;

    $("#q-par").classList.toggle(
        "hidden",
        !c.parametrizada
    );
}

$("#q-sel").onchange = cambiarConsulta;

// =====================================================
// EJECUTAR CONSULTA
// =====================================================

$("#q-run").onclick = async () => {
    try {
        const r = await api(
            "/api/consultas/" + $("#q-sel").selectedIndex,
            "POST",
            {
                inicio: $("#q-ini").value.replace("T", " "),
                fin: $("#q-fin").value.replace("T", " "),
                sede: $("#q-sede").value,
                tipo: $("#q-tipo").value
            }
        );

        dibujar(
            $("#q-grid"),
            r.columnas,
            r.filas
        );

        $("#q-total").textContent =
            `${r.filas.length} resultado(s)`;

    } catch (e) {
        fallo(e, "No se pudo ejecutar la consulta");
    }
};
