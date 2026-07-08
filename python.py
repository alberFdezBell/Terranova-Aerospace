import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import krpc
import threading
import time
import math

class ControladorOrbitalNativo:
    """Clase encargada de la astrodinámica utilizando el SAS nativo de KSP y control de cámaras."""
    def __init__(self, conn):
        self.conn = conn
        self.space_center = conn.space_center

    def obtener_vessel_seguro(self, vessel_original):
        try:
            return self.space_center.active_vessel
        except Exception:
            return vessel_original

    def inyectar_orbita_resonante_sas(self, vessel, altitud_objetivo_km, num_sat, timeout_max=120):
        vessel = self.obtener_vessel_seguro(vessel)
        body = vessel.orbit.body
        mu = body.gravitational_parameter
        
        r_destino = (altitud_objetivo_km * 1000.0) + body.equatorial_radius
        periodo_destino = 2 * math.pi * math.sqrt((r_destino**3) / mu)
        
        periodo_transferencia = periodo_destino * ((num_sat + 1) / num_sat)
        a_transferencia = (mu * (periodo_transferencia / (2 * math.pi))**2)**(1.0/3.0)
        
        r_actual = vessel.orbit.semi_major_axis
        v_deseada = math.sqrt(mu * (2.0 / r_actual - 1.0 / a_transferencia))
        
        print("[Orbital] Viajando al punto óptimo para iniciar maniobra...")
        if vessel.orbit.time_to_periapsis < vessel.orbit.time_to_apoapsis:
            self.viajar_a_punto_seguro(vessel, vessel.orbit.time_to_periapsis)
        else:
            self.viajar_a_punto_seguro(vessel, vessel.orbit.time_to_apoapsis)

        print("[SAS] Activando SAS en modo PROGRADO...")
        vessel.control.sas = True
        time.sleep(0.2)
        vessel.control.sas_mode = self.space_center.SASMode.prograde
        
        print("[Orbital] Esperando 10 segundos para estabilización de apuntado...")
        time.sleep(10)

        print("[Orbital] Iniciando quema de inyección...")
        vessel.control.throttle = 0.6
        inicio_quema = time.time()
        
        while True:
            if time.time() - inicio_quema > timeout_max:
                break
            v_actual = math.sqrt(mu * (2.0 / r_actual - 1.0 / vessel.orbit.semi_major_axis))
            if (v_deseada - v_actual) <= 0.15: 
                break
            time.sleep(0.05)
            
        vessel.control.throttle = 0.0
        print("-> [Orbital] Órbita elíptica resonante establecida.")
        return periodo_destino

    def viajar_a_punto_seguro(self, vessel, tiempo_restante, margen_segundos=15):
        if tiempo_restante > margen_segundos:
            print(f"[Orbital] Warp temporal activo. Saltando {int(tiempo_restante - margen_segundos)}s...")
            self.space_center.warp_to(self.space_center.ut + tiempo_restante - margen_segundos)
            time.sleep(margen_segundos + 2)

    def circularizar_satelite_sas(self, satelite, periodo_objetivo):
        try:
            print(f"[Cámara] Cambiando enfoque a: {satelite.name}")
            self.space_center.active_vessel = satelite
            time.sleep(1.5)

            print(f"[SAS] {satelite.name} activando SAS en modo Progrado...")
            satelite.control.sas = True
            time.sleep(0.2)
            satelite.control.sas_mode = self.space_center.SASMode.prograde
            
            print(f"[Orbital] Orientando satélite...")
            time.sleep(8.0)
            
            print(f"[Orbital] {satelite.name} -> ¡Encendiendo motores de circularización!")
            satelite.control.throttle = 1.0
            
            while satelite.orbit.period < (periodo_objetivo - 0.2):
                time.sleep(0.05)
                
            satelite.control.throttle = 0.0
            print(f"-> [Orbital] {satelite.name} asentado en órbita circular.")
            
        except Exception as e:
            print(f"[⚠️ Error en Satélite] {satelite.name}: {e}")
            satelite.control.throttle = 0.0


class PanelControlKSP:
    def __init__(self, root):
        self.root = root
        self.root.title("Consola Avanzada KSP")
        self.root.geometry("360x320")
        self.running = True
        
        try:
            self.conn = krpc.connect(name='Consola Avanzada')
            self.orbital_core = ControladorOrbitalNativo(self.conn)
        except Exception as e:
            messagebox.showerror("Error de Conexión", f"No se pudo conectar a kRPC: {e}")
            self.root.destroy()
            return

        self.bloqueo_bucle = False
        self.root.protocol("WM_DELETE_WINDOW", self.cerrar_aplicacion)

        # --- INTERFAZ PRINCIPAL ---
        self.boton_rcs = tk.Button(
            root, text="RCS (Requiere Nave)", font=("Arial", 11, "bold"),
            command=self.alternar_rcs_desde_click,
            bg="lightgray", fg="black", height=2, width=22
        )
        self.boton_rcs.pack(pady=15)

        self.boton_config_desacoples = tk.Button(
            root, text="🚀 Configurar Despliegues", font=("Arial", 11, "bold"),
            command=self.escanear_y_abrir_menu,
            bg="#28A745", fg="white", height=2, width=24
        )
        self.boton_config_desacoples.pack(pady=10)

        self.boton_renombrar_global = tk.Button(
            root, text="🛰️ Nombramiento de Satélites", font=("Arial", 11, "bold"),
            command=self.abrir_ventana_renombrar_global,
            bg="#17A2B8", fg="white", height=2, width=24
        )
        self.boton_renombrar_global.pack(pady=10)

        threading.Thread(target=self.bucle_escucha_ksp, daemon=True).start()

    def cerrar_aplicacion(self):
        self.running = False
        self.root.destroy()

    def alternar_rcs_desde_click(self):
        self.bloqueo_bucle = True
        try:
            vessel_actual = self.conn.space_center.active_vessel
            if vessel_actual is None: raise Exception
            nuevo_estado = not vessel_actual.control.rcs
            vessel_actual.control.rcs = nuevo_estado
            self.boton_rcs.config(text="RCS", bg="#007BFF" if nuevo_estado else "lightgray", fg="white" if nuevo_estado else "black")
        except:
            messagebox.showwarning("Acción no disponible", "Debes controlar una nave para usar RCS.")
        finally:
            self.bloqueo_bucle = False

    def bucle_escucha_ksp(self):
        while self.running and self.root.winfo_exists():
            if not self.bloqueo_bucle:
                try:
                    vessel_actual = self.conn.space_center.active_vessel
                    if vessel_actual:
                        estado = vessel_actual.control.rcs
                        if self.running:
                            self.root.after(0, lambda e=estado: self.actualizar_boton_rcs(e, True))
                    else:
                        self.root.after(0, lambda: self.actualizar_boton_rcs(False, False))
                except:
                    self.root.after(0, lambda: self.actualizar_boton_rcs(False, False))
            time.sleep(0.4)

    def actualizar_boton_rcs(self, estado, nave_activa):
        if self.running and self.root.winfo_exists():
            if nave_activa:
                self.boton_rcs.config(text="RCS", bg="#007BFF" if estado else "lightgray", fg="white" if estado else "black")
            else:
                self.boton_rcs.config(text="RCS (Sin nave activa)", bg="lightgray", fg="gray")


    # =========================================================================
    # ESCANEO ABSOLUTO FORZADO (BYPASSEANDO EL ALMACENAMIENTO DE ESCENA)
    # =========================================================================
    def abrir_ventana_renombrar_global(self):
        try:
            # Forzamos la obtención directa sin filtros intermedios del simulador
            self.todas_las_naves_globales = list(self.conn.space_center.vessels)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo forzar el escaneo del universo: {e}")
            return

        self.win_renombrar = tk.Toplevel(self.root)
        self.win_renombrar.title("Rastreador Definitivo de Satélites")
        self.win_renombrar.geometry("660x500")
        self.win_renombrar.grab_set()

        # --- PANEL SUPERIOR DE FILTRADO ---
        frame_filtro = tk.Frame(self.win_renombrar, pady=5)
        frame_filtro.pack(fill="x")
        
        tk.Label(frame_filtro, text="Filtrar por categoría KSP: ", font=("Arial", 9, "bold")).pack(side="left", padx=10)
        
        self.combo_filtro = ttk.Combobox(
            frame_filtro, 
            values=["TODOS (Sondas, Relés, Estaciones, Naves, Bases)", "PROBE (Sondas)", "RELAY (Antenas/Relés)", "STATION (Estaciones)", "SHIP (Cohetes/Naves)", "BASE (Asentamientos)"],
            state="readonly", width=45
        )
        self.combo_filtro.current(0)
        self.combo_filtro.pack(side="left", padx=5)
        self.combo_filtro.bind("<<ComboboxSelected>>", lambda event: self.renderizar_lista_satelites())

        # --- CONTENEDOR SCROLLABLE ---
        self.container_lista = tk.Frame(self.win_renombrar)
        self.container_lista.pack(fill="both", expand=True, padx=5, pady=5)

        # Lanzamos la renderización por primera vez
        self.renderizar_lista_satelites()

    def renderizar_lista_satelites(self):
        # Limpiar contenedor si ya tenía datos previos
        for widget in self.container_lista.winfo_children():
            widget.destroy()

        canvas = tk.Canvas(self.container_lista, borderwidth=0, background="#f5f5f5")
        scrollbar = tk.Scrollbar(self.container_lista, orient="vertical", command=canvas.yview)
        frame_scrollable = tk.Frame(canvas, background="#f5f5f5")

        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.create_window((0, 0), window=frame_scrollable, anchor="nw")

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        frame_scrollable.bind("<Configure>", _on_frame_configure)

        # Encabezados
        tk.Label(frame_scrollable, text="Nombre Registrado en el Universo", font=("Arial", 10, "bold"), width=32, anchor="w", bg="#f5f5f5").grid(row=0, column=0, padx=10, pady=10)
        tk.Label(frame_scrollable, text="Nuevo Nombre", font=("Arial", 10, "bold"), width=25, anchor="w", bg="#f5f5f5").grid(row=0, column=1, padx=5, pady=10)
        tk.Label(frame_scrollable, text="Acción", font=("Arial", 10, "bold"), width=12, bg="#f5f5f5").grid(row=0, column=2, padx=5, pady=10)

        filtro_seleccionado = self.combo_filtro.get()
        
        # Mapeo de tipos admisibles (eliminando basura y asteroides de forma segura)
        tipos_mapeo = {
            "PROBE": [self.conn.space_center.VesselType.probe],
            "RELAY": [self.conn.space_center.VesselType.relay],
            "STATION": [self.conn.space_center.VesselType.station],
            "SHIP": [self.conn.space_center.VesselType.ship, self.conn.space_center.VesselType.lander],
            "BASE": [self.conn.space_center.VesselType.base]
        }
        
        if "TODOS" in filtro_seleccionado:
            tipos_validos = tipos_mapeo["PROBE"] + tipos_mapeo["RELAY"] + tipos_mapeo["STATION"] + tipos_mapeo["SHIP"] + tipos_mapeo["BASE"]
        else:
            clave = filtro_seleccionado.split(" ")[0]
            tipos_validos = tipos_mapeo.get(clave, [])

        naves_filtradas = []
        for v in self.todas_las_naves_globales:
            try:
                # Comprobación cruda: saltamos cualquier elemento corrupto o descargado parcialmente
                if v and v.name and v.type in tipos_validos:
                    naves_filtradas.append(v)
            except:
                continue

        # Ordenar alfabéticamente
        naves_filtradas.sort(key=lambda x: x.name.lower())

        self.diccionario_entradas = {}

        for index, nave in enumerate(naves_filtradas):
            try:
                nombre_actual = nave.name
                tipo_nave = str(nave.type).split('.')[-1].upper()
            except:
                continue

            lbl_texto = f"[{tipo_nave}]  {nombre_actual}"
            lbl_nombre = tk.Label(frame_scrollable, text=lbl_texto, font=("Arial", 9), anchor="w", bg="#f5f5f5")
            lbl_nombre.grid(row=index+1, column=0, padx=10, pady=4, sticky="w")

            ent_nuevo_nombre = tk.Entry(frame_scrollable, font=("Arial", 9), width=25)
            ent_nuevo_nombre.insert(0, nombre_actual)
            ent_nuevo_nombre.grid(row=index+1, column=1, padx=5, pady=4)

            self.diccionario_entradas[nave] = {
                "entry": ent_nuevo_nombre,
                "label": lbl_nombre,
                "tipo": tipo_nave
            }

            btn_guardar = tk.Button(
                frame_scrollable, text="Renombrar", bg="#17A2B8", fg="white", font=("Arial", 8, "bold"),
                command=lambda n=nave: self.aplicar_renombre_satelite(n)
            )
            btn_guardar.grid(row=index+1, column=2, padx=5, pady=4)

    def aplicar_renombre_satelite(self, nave):
        try:
            nuevo_nombre = self.diccionario_entradas[nave]["entry"].get().strip()
            if not nuevo_nombre:
                messagebox.showwarning("Atención", "El nombre no puede estar vacío.")
                return
            
            # Inyección directa en el Core de persistencia de KSP
            nave.name = nuevo_nombre
            tipo_txt = self.diccionario_entradas[nave]["tipo"]
            self.diccionario_entradas[nave]["label"].config(text=f"[{tipo_txt}]  {nuevo_nombre}")
            print(f"[Remoto] Objeto renombrado con éxito a: {nuevo_nombre}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo modificar de forma remota: {e}")

    # =========================================================================
    # LÓGICA DE DESPLIEGUE (SE MANTIENE INTACTA)
    # =========================================================================
    def escanear_y_abrir_menu(self):
        try:
            self.vessel = self.conn.space_center.active_vessel
            if self.vessel is None: raise Exception
            desacopladores = self.vessel.parts.decouplers
        except:
            messagebox.showerror("Error de Entorno", "Para configurar despliegues debes controlar una nave en vuelo.")
            return

        if not desacopladores:
            messagebox.showerror("Error", "No se detectó ningún desacoplador en la nave actual.")
            return

        self.datos_satelites = []
        for i, dec in enumerate(desacopladores):
            self.datos_satelites.append({
                "decoupler": dec,
                "nombre_defecto": f"Satélite-{i+1}",
                "entry_widget": None,
                "progrado_var": tk.BooleanVar(value=True)
            })
        
        self.datos_satelites.sort(key=lambda x: x["decoupler"].part.stage, reverse=True)

        self.ventana_nombres = tk.Toplevel(self.root)
        self.ventana_nombres.title("Organizar Constelación")
        self.ventana_nombres.geometry(f"880x{220 + (len(desacopladores) * 45)}")
        self.ventana_nombres.grab_set()

        self.frame_lista = tk.Frame(self.ventana_nombres)
        self.frame_lista.pack(fill="both", expand=True, padx=10, pady=10)

        self.actualizar_interfaz_lista()

        self.formacion_var = tk.BooleanVar(value=False)
        chk_formacion = tk.Checkbutton(
            self.ventana_nombres, 
            text="✨ Activar Secuencia con Saltos de Cámara Dinámicos (SAS Nativo KSP)",
            variable=self.formacion_var,
            font=("Arial", 10, "bold"),
            fg="#28A745"
        )
        chk_formacion.pack(pady=5)

        btn_confirmar = tk.Button(
            self.ventana_nombres, text="🚀 ¡Iniciar Secuencia Automatizada!",
            bg="#DC3545", fg="white", font=("Arial", 11, "bold"), height=2,
            command=self.iniciar_secuencia
        )
        btn_confirmar.pack(pady=10)

    def actualizar_interfaz_lista(self):
        for widget in self.frame_lista.winfo_children():
            widget.destroy()

        tk.Label(self.frame_lista, text="Orden / Etapa", font=("Arial", 9, "bold"), width=12).grid(row=0, column=0)
        tk.Label(self.frame_lista, text="Pieza en KSP", font=("Arial", 9, "bold"), width=20).grid(row=0, column=1)
        tk.Label(self.frame_lista, text="Nombre del Satélite", font=("Arial", 9, "bold"), width=20).grid(row=0, column=2)
        tk.Label(self.frame_lista, text="Automatización", font=("Arial", 9, "bold"), width=22).grid(row=0, column=3)
        tk.Label(self.frame_lista, text="Acciones", font=("Arial", 9, "bold"), width=20).grid(row=0, column=4)

        for index, item in enumerate(self.datos_satelites):
            dec = item["decoupler"]
            
            tk.Label(self.frame_lista, text=f"#{index+1} (Etapa {dec.part.stage})", fg="blue").grid(row=index+1, column=0, pady=5)
            tk.Label(self.frame_lista, text=f"{dec.part.title[:18]}...", anchor="w").grid(row=index+1, column=1, padx=5)

            txt_entry = tk.Entry(self.frame_lista, width=20)
            txt_entry.insert(0, item["nombre_defecto"])
            txt_entry.grid(row=index+1, column=2, padx=5)
            item["entry_widget"] = txt_entry

            chk_progrado = tk.Checkbutton(self.frame_lista, text="Auto-Circularizar al soltar", variable=item["progrado_var"])
            chk_progrado.grid(row=index+1, column=3, padx=5)

            frame_botones = tk.Frame(self.frame_lista)
            frame_botones.grid(row=index+1, column=4, padx=5)

            btn_up = tk.Button(frame_botones, text="▲", command=lambda idx=index: self.mover_satelite(idx, -1))
            btn_down = tk.Button(frame_botones, text="▼", command=lambda idx=index: self.mover_satelite(idx, 1))
            
            btn_id = tk.Button(frame_botones, text="👁 Identificar", bg="#FFC107")
            btn_id.bind("<Enter>", lambda event, d=dec: self.resaltar_pieza(d, True))
            btn_id.bind("<Leave>", lambda event, d=dec: self.resaltar_pieza(d, False))

            if index == 0: btn_up.config(state="disabled")
            if index == len(self.datos_satelites) - 1: btn_down.config(state="disabled")

            btn_up.pack(side="left", padx=2)
            btn_down.pack(side="left", padx=2)
            btn_id.pack(side="left", padx=5)

    def mover_satelite(self, index, direccion):
        nueva_pos = index + direccion
        if not (0 <= nueva_pos < len(self.datos_satelites)):
            return

        for item in self.datos_satelites:
            if item["entry_widget"]:
                item["nombre_defecto"] = item["entry_widget"].get()

        self.datos_satelites[index], self.datos_satelites[nueva_pos] = self.datos_satelites[nueva_pos], self.datos_satelites[index]
        self.actualizar_interfaz_lista()

    def resaltar_pieza(self, decoupler, activar):
        try: decoupler.part.highlighted = activar
        except: pass

    def iniciar_secuencia(self):
        nombres_finales = []
        opciones_progrado = []
        for item in self.datos_satelites:
            nombre = item["entry_widget"].get().strip()
            if not nombre:
                messagebox.showwarning("Campos vacíos", "Todos los satélites deben tener un nombre.")
                return
            nombres_finales.append(nombre)
            opciones_progrado.append(item["progrado_var"].get())

        en_formacion = self.formacion_var.get()
        altitud_objetivo_km = 0.0

        if en_formacion:
            if len(nombres_finales) < 2:
                en_formacion = False
            else:
                altitud_objetivo_km = simpledialog.askfloat(
                    "Órbita Objetivo",
                    "Introduce la ALTITUD final de la constelación (en Kilómetros):",
                    initialvalue=300.0, minvalue=75.0, maxvalue=60000.0
                )
                if altitud_objetivo_km is None: return

        self.ventana_nombres.destroy()
        
        threading.Thread(
            target=self.ejecutar_desacoples, 
            args=(nombres_finales, opciones_progrado, en_formacion, altitud_objetivo_km), 
            daemon=True
        ).start()

    def ejecutar_desacoples(self, lista_nombres, lista_progrado, en_formacion, altitud_km):
        try:
            self.root.after(0, lambda: self.boton_config_desacoples.config(state="disabled", text="Misión en curso..."))
            
            cohete_madre = self.conn.space_center.active_vessel
            num_sat = len(lista_nombres)

            if en_formacion:
                periodo_destino_calculado = self.orbital_core.inyectar_orbita_resonante_sas(cohete_madre, altitud_km, num_sat)
            else:
                periodo_destino_calculado = cohete_madre.orbit.period

            for i, nombre in enumerate(lista_nombres):
                print(f"[Cámara] Devolviendo enfoque a la nave nodriza para preparar suelta...")
                self.conn.space_center.active_vessel = cohete_madre
                time.sleep(1.5)
                cohete_madre = self.orbital_core.obtener_vessel_seguro(cohete_madre)

                if en_formacion:
                    cohete_madre.control.sas = True
                    cohete_madre.control.sas_mode = self.space_center.SASMode.prograde
                    self.orbital_core.viajar_a_punto_seguro(cohete_madre, cohete_madre.orbit.time_to_apoapsis)

                print(f"Liberando #{i+1}: {nombre}")
                dec = self.datos_satelites[i]["decoupler"]
                quiere_progrado = lista_progrado[i]
                
                naves_antes = set(self.conn.space_center.vessels)
                try:
                    dec.decouple()
                except Exception as e:
                    print(f"[⚠️ Error] No se pudo desacoplar: {e}")
                    continue

                time.sleep(1.5)
                naves_despues = set(self.conn.space_center.vessels)
                nuevas_naves = naves_despues - naves_antes

                if len(nuevas_naves) >= 1:
                    satelite = nuevas_naves.pop() 
                    satelite.name = nombre

                    if quiere_progrado and en_formacion:
                        self.orbital_core.circularizar_satelite_sas(satelite, periodo_destino_calculado)
                else:
                    print(f"⚠️ No se detectó la nueva pieza desprendida.")

            self.conn.space_center.active_vessel = cohete_madre
            msg = f"¡Constelación desplegada! La vista ha regresado a la nave nodriza."
            self.root.after(0, lambda: messagebox.showinfo("Misión Completada", msg))
            
        except Exception as e:
            mensaje_error = str(e)
            self.root.after(0, lambda err=mensaje_error: messagebox.showerror("Error", f"Fallo en la ejecución:\n{err}"))
        finally:
            try: self.conn.space_center.active_vessel = cohete_madre
            except: pass
            self.root.after(0, lambda: self.boton_config_desacoples.config(state="normal", text="Configurar Despliegues"))

if __name__ == "__main__":
    ventana = tk.Tk()
    app = PanelControlKSP(ventana)
    ventana.mainloop()