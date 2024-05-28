from mysql.connector import errorcode
from datetime import datetime
import mysql.connector
import threading
import socket
import copy
import time
import sys
import re
import ast


class Tickets:
    def __init__(self, indice_host):
        # IP Y PUERTO DE LOS NODOS EN EL SD
        self.nodos = [
            {"ip": "192.168.100.129", "port": 5555},
            {"ip": "192.168.100.130", "port": 5555},
            {"ip": "192.168.100.131", "port": 5555},
            {"ip": "192.168.100.132", "port": 5555}
        ]
        self.mi_indice = indice_host
        self.host = self.nodos[copy.copy(self.mi_indice)]
        # LISTA CON mysLOS INDICES DE LOS NODOS ACTIVOS
        self.nodos_activos = []        
        # TIEMPOS DE ESPERA PARA CADA UNO DE LOS HILOS, Y/O RESPUESTA DE LOS NODOS
        # TIEMPO DE ESPERA ENTRE VERIFICACION
        self.tiempo_verificacion_heartbeat = 2
        self.tiempo_espera_eleccion = 2
        # TOLERANCIA PARA RESPUESTA DEL HEARTBEAR
        self.tolerancia_heartbeat = 5
        self.espera_ack_eleccion = 3
        # ASIGNAMOS EL TIEMPO EN EL QUE INICIO LA ELECCION, DEBE TENER ALGUN VALOR AL INICIAR
        # EL PROGRAMA
        self.tiempo_eleccion = 0.0
        # ESPERA PARA ENVIO DE HEARTBEAT A LOS DEMAS NODOS
        self.espera_heartbeat = 2
        # TOLERANCIA MAXIMA PARA SOLTAR A UN INGENIERO PRESELECCIONADO
        self.tolerancia_exclusion_ing = 5

        # BANDERAS PARA LA SELECCION Y PARA SABER SI ES NODO MAESTRO
        self.soy_maestro = False
        self.nodo_maestro = None
        self.hay_eleccion =ACK False
        self.ack_eleccion = False

        # LISTA CON LOS ID DE LOS DISPOSITIVOS EN CADA NODO
        self.lista_distribucion = [[] for _ in range(len(self.nodos))]
        # LISTA CON LOS ULTIMOS HEARTBEATS PARA COMPARARLOS EN VERIFICAR HEARTBEAT
        self.ultimo_heartbeat = [0 for i in range (len(self.nodos))]       
        # LISTA CON LOS ID DE LOS DISPOSITIVOS DEL HOST
        self.mis_dispositivos = []
        # LISTA CON LOS INGENIEROS PRESELECCIONADOS (EXCLUSION MUTUA)
        self.inges_preseleccionados = []
        self.mi_preseleccion = None
        self.num_ack_preseleccion = 0
        self.bandera_exclusion = False
        # LISTAS CON LOS DATOS DE LA BASE DE DATOS
        self.lista_sucursales = []        
        self.lista_tickets = []
        self.lista_dispos = [] 
        self.lista_users = []
        self.lista_ing = []

        # Variables de control para la base de datos
        self.bd_lock = threading.Lock()
        self.query_distribuida = ""
        self.espera_bd_distribuida = 2;


        # CONFIGURACION DE LA BASE DE DATOS
        self.config_bd = {
            'user': 'root',
            'password': 'contrasenaSegur4!',
            'host': self.nodos[indice_host]["ip"],
            'database': 'Distribuidos',
            'raise_on_warnings': True
        }

        # VARIABLES PARA LA CONEXION A LA BASE DE DATOS
        self.conexion_bd = None
        self.cursor = None

        # NOMBRE DEL ARCHIVO PARA GUARDAR EL ENVIO DE MENSAJES ENTRE NODOS
        self.log_file = f"mensajes_log_{indice_host}.txt"
        # ELIMINAMOS (SI EXISTE) EL ARCHIVO Y CREAMOS UNO NUEVO
        open(self.log_file, "w")

        # BANDEARE DE REDISTRIBUCION
        self.hay_redistribucion = False

        # SOCKET
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # REALIZAMOS LAS CONEXIONES CON EL SOCKET Y LA BASE DE DATOS
        self.connect_socket()
        self.connect_database()
        # INICIAMOS LOS HILOS QUE UTILIZAREMOS
        self.iniciar_hilos()
        # FUNCION QUE ENVIA A TODOS LOS NODOS MENSAJE DE QUE NOS ACABAMOS DE ACTIVAR
        self.raising()
        # SI SOMOS EL UNICO NODO ACTIVO, REALIZAMOS LA DISTRIBUCION DE LOS DISPOSITIVOS
        if not len(self.nodos_activos):
            self.iniciar_distribucion()

        # DESPLEGAMOS EL MENU AL USUARIO Y REALIZAMOS LAS ACCIONES CORRESPONDIENTES A LA ELECCION 
        # DEL USUARIO
        self.menu()

    # REALIZAMOS EL BINDING
    def connect_socket(self):
        try:
            self.socket.bind((self.host["ip"], self.host["port"]))
        except OSError as e:
            print(f"Error: {e}")
            self.close()

    # NOS CONECTAMOS A LA BASE DE DATOS
    def connect_database(self):
        try:
            # NOS CONECTAMOS A LA BASE DE DATOS CON LA CONFIGURACION INICIAL
            self.conexion_bd = mysql.connector.connect(**self.config_bd)
            # cURSOS QUE NOS PERMITIRA REALIZAR ACCIONES EN LA BASE DE DATOS
            self.cursor = self.conexion_bd.cursor()
            # GUARDAMOS LOS DATOS DE LA BASE EN LAS LISTAS 
            self.cargar_datos_db()
        # MANEJO DE ERRORES
        except mysql.connector.Error as err:
            self.db_error(err)

    # MANEJO DE ERRORES EN LA BASE DE DATOS
    def db_error(self, err):
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            print("Usuario o contraseña incorrecta")

        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            print("La base de datos no existe")
        elif err.errno == errorcode.ER_ROW_IS_REFERENCED_2:
            print(f"Error de clave foránea al actualizar el dispositivo {id_dispo}: {err}")
        else:
            print(f'Error de base de datos: {err}')

    # CARGAMOS LOS DATOS DE LA BASE EN LAS LISTAS 
    def cargar_datos_db(self):
        try:
            # INICIAMOS EL CURSOR NUEVAMENTE, DEBIDO A QUE TENEMOS QUE CERRARLO DESPUES DE CADA USO
            # AL USAR HILOS, PODRIAN QUEDAR ACCIONES PENDIENTES, ENTONCES LO CERRAMOS AL FINALIZAR
            # PARA ASI QUITAR LAS ACCIONES PENDIENTES Y NO CAUSAR ERRORES AL REPLICAR LA BASE
            self.cursor = self.conexion_bd.cursor()
            self.cursor.execute("SELECT * FROM Dispos")
            self.lista_dispos = self.cursor.fetchall()
            self.cursor.execute("SELECT * FROM Ingenieros")
            self.lista_ing = self.cursor.fetchall()
            self.cursor.execute("SELECT * FROM User")
            self.lista_users = self.cursor.fetchall()
            self.cursor.execute("SELECT * FROM Ticket")
            self.lista_tickets = self.cursor.fetchall()
            self.cursor.execute("SELECT * FROM Sucursal")
            self.lista_sucursales = self.cursor.fetchall()
        except mysql.connector.Error as err:
            self.db_error(err)
        finally:
            self.cursor.close()

    # REALIZA UNA ACCION EN LA BASE DE DATOS
    def agregar_a_la_base(self, query, params):
        with self.bd_lock:
            try:
                # CREAMOS UN CURSOR PARA REALIZAR ACCIONES Y LO CERRAMOS AL FINALIZAR
                self.cursor = self.conexion_bd.cursor()
                # Hacemos commit
                self.do_commit(query, params)
                # CARGAMOS NUEVAMENTE LOS DATOS EN LAS LISTAS PARA QUE SE ACTUALICEN SEGUN LA BASE
                # DE DATOS
                self.cargar_datos_db()
            except mysql.connector.Error as err:
                self.db_error(err)
            finally:
                self.cursor.close()

    # Hacemos commit
    def do_commit(self, query, params):
        self.cursor.execute(query, params)
        self.conexion_bd.commit()
        self.enviar_mensaje_activos(f"commit <{query}> ({','.join(map(str, params))})")

    # Hacemos un casteo del valor si es posible
    def convertir_valor(self, valor):
        # Eliminar espacios en blanco alrededor del valor
        valor = valor.strip()  
        try:
            valor = int(valor)  
        except ValueError:
            try:
                valor = float(valor)  
            except ValueError:
                try:
                    valor = datetime.strptime(valor, '%Y-%m-%d %H:%M:%S') 
                except ValueError:
                    pass  # Si no se puede convertir, mantener como cadena
        return valor

    # Separamos la instruccion para hacer commit en la base de datos
    def analizar_commit(self):
        while True and len(self.query_distribuida) and self.conexion_bd != None:
            with self.bd_lock:
                try:
                    # CREAMOS UN CURSOR PARA REALIZAR ACCIONES Y LO CERRAMOS AL FINALIZAR
                    self.cursor = self.conexion_bd.cursor()
                    # Expresión regular para extraer la consulta y los parámetros
                    regex = r"commit\s*<(.*?)>\s*\((.*?)\)"


                    coincidencia = re.search(regex, self.query_distribuida)

                    if coincidencia:
                        consulta = coincidencia.group(1)
                        parametros_str = coincidencia.group(2)
                        # Suponiendo que los parámetros están separados por comas
                        parametros = parametros_str.split(',')  

                        # Convertir los parámetros a sus tipos de datos correspondientes
                        parametros_convertidos = [self.convertir_valor(parametro) 
                            for parametro in parametros]
                        self.cursor.execute(consulta, parametros_convertidos)
                        self.conexion_bd.commit()
                        self.cargar_datos_db()
                    else:
                except mysql.connector.Error as err:
                    self.db_error(err)
                finally:
                    self.cursor.close()
                    self.query_distribuida = ""
            time.sleep(self.espera_bd_distribuida)

        
    
    # INICIAMOS LOS HILOS 
    def iniciar_hilos(self):
        # ESCUCHAMOS LOS MENSAJES DE OTROS NODOS
        self.receive_thread = threading.Thread(target=self.receive)
        self.receive_thread.start()
        # VERIFICAMOS SI ALGUN NODO CAE
        self.verificacion_heartbeat_thread = threading.Thread(target=self.verificar_nodos_activos)
        self.verificacion_heartbeat_thread.start()
        # CHECAMOS EL PROCESO DE ELECCION
        self.eleccion_thread = threading.Thread(target=self.verificar_eleccion)
        self.eleccion_thread.start()
        # ENVIAMOS CONOCIMIENTO A LOS NODOS DE NUESTRA EXISTENCIA
        self.heartbeat_thread = threading.Thread(target=self.heartbeat)
        self.heartbeat_thread.start()

    # MENU 
    def menu(self):
        while True:
            # PODEMOS INGRESAR COMO USUARIO, INGENIERO O ADMIN
            # VERIFICAMOS QUE LA ENTRADA SEA UN ENTERO
            ingreso = self.verificar_entrada(
                "Ingresar como: \n\t 1. Usuario\n\t 2. Ingeniero\n\t 3. Administrador\n", int)
            if ingreso == 1:
                self.menu_usuario()
            elif ingreso == 2:
                self.menu_ingeniero()
            elif ingreso == 3:
                self.menu_administrador()
            else:
                print("Opción no válida")

    def comenzar_hilo(self):
        self.base_distribuida_thread = threading.Thread(target=self.analizar_commit)
        self.base_distribuida_thread.start()

    # VERIFICAMOS QUE LA ENTRADA CORRESPONDA CON EL TIPO DE DATO (INT, FLOAT) DE FORMA RECURSIVA
    def verificar_entrada(self, mensaje, tipo_dato):
        try:
            return tipo_dato(input(mensaje))
        except ValueError:
            print("Ingrese un valor válido")
            return self.verificar_entrada(mensaje, tipo_dato)

    # MENU DE LAS ACCIONES QUE PUEDE REALIZAR UN USUARIO
    def menu_usuario(self):
        accion = self.verificar_entrada(
            "Qué haremos hoy?: \n\t 1. Levantar ticket\n\t 2. Ver dispositivos\n\t 3. Ver tickets\n", int)
        if accion == 1:
            self.levantar_tiket()
        elif accion == 2:
            self.mostrar_dispos()
            pass
        elif accion == 3:
            self.mostrar_tickets()
        else:
            print("Opción no válida")

    # MENU DE LAS ACCIONES QUE PUEDE REALIZAR UN INGENIERO
    def menu_ingeniero(self):
        accion = self.verificar_entrada(
            "Qué haremos hoy?: \n\t 1. Cerrar ticket\n\t 2. Ver dispositivos\n\t 3. Ver tickets\n", int)
        if accion == 1:
            self.cerrar_ticket()
        elif accion == 2:
            self.mostrar_dispos()
        elif accion == 3:
            self.mostrar_tickets()
        else:
            print("Opción no válida")

    # MENU DE LAS ACCIONES QUE PUEDE REALIZAR EL ADMINISTRADOR
    def menu_administrador(self):
        accion = self.verificar_entrada(
            "Qué haremos hoy?: \n\t 1. Ver dispositivos\n\t 2. Ver tickets\n\t 3. Ver ingenieros\n\t 4. Ver usuarios\n\t 5. Agregar dispositivo\n\t 6. Agregar ingeniero\n\t 7. Agregar usuario\n\t 8. Actualizar dispositivo\n\t 9. Actualizar ingeniero\n\t 10. Actualizar usuario\n",
            int)
        if accion == 1:
            self.mostrar_dispos()
        elif accion == 2:
            self.mostrar_tickets()
        elif accion == 3:
            self.mostrar_inges()
        elif accion == 4:
            self.mostrar_usuarios()
        elif accion == 5:
            self.agregar_dispositivo()
        elif accion == 6:
            self.agregar_ingeniero()
        elif accion == 7:
            self.agregar_usuario()
        elif accion == 8:
            self.actualizar_dispo()
        elif accion == 9:
            self.actualizar_ingeniero()
        elif accion == 10:
            self.actualizar_usuario()
        else:
            print("Opción no válida")

    # FUNCION PARA LEVANTAR TICKET [USUARIO]
    def levantar_tiket(self):
        # SI NO HAY INGENIEROS LIBRES, NO PODEMOS LEVANTAR TICKETS
        if not self.hay_ingeniero_libre():
            print("Por el momento todos nuestros ingenieros estan ocupado.\n Por favor intentelo mas tarde")
        else:
            try:
                # PEDIMOS TODOS LOS DATOS AL USUARIOS Y VERIFICAMOS LAS ENTRADAS
                self.mostrar_usuarios()
                id_usuario = self.verificar_entrada(
                    "Ingrese su id ",int)
                while(id_usuario > len(self.lista_users)):
                    id_dispo = self.verificar_entrada(
                    "Ingrese un id valido ",int)
                self.mostrar_dispos()
                id_dispo = self.verificar_entrada(
                    "Ingrese el id del dispositivo ",int)
                while(id_dispo > len(self.lista_dispos) ):
                    id_dispo = self.verificar_entrada(
                    "Ingrese el id valido del dispositivo ",int)
                fecha_creacion = datetime.now().strftime("%Y-%m-%d %H:%M:%S" )
                estado = 'Abierto'
                ingeniero_asignado = self.asignar_ingeniero()
                if ingeniero_asignado == -1:
                    print("Ocurrio un problema al asignar ingeniero")
                else:
                    if self.exclusion_mutua_ing(ingeniero_asignado):
                        id_sucursal = self.obtener_sucursal(id_dispo)
                        if id_sucursal == -1:
                            print("Ocurrio un problema al ubicar el dispositivo")
                        else:
                            # CREAMOS Y ASIGNAMOS EL FOLIO
                            folio = f"{id_usuario}-{ingeniero_asignado}-{id_sucursal}-{len(self.lista_tickets)}"
                            descripcion = input("ingrese la descripcion del problema: ")
                            self.agregar_a_la_base(
                                "INSERT INTO Ticket (folio, descripcion, fecha_creacion, estado, id_dispositivo, id_ingeniero)"
                                "VALUES (%s, %s, %s, %s, %s, %s)", (folio, descripcion, fecha_creacion, estado, id_dispo, ingeniero_asignado))
                    else:
                        print("El ingeniero esta siendo modificado por otro nodo")
            except mysql.connector.Error as err:
                self.db_error(err)
            finally:
                print("Ticket levantado correctamente")
    
    # VERIFICAMOS QUE EL ID DEL INGE NO LO HAYA PRESELECCIONADO OTRO NODO
    def exclusion_mutua_ing(self, id_inge):
        # GUARDAMOS NUESTRA SELECCION Y GUARDAMOS EL NUMERO DE RESPUESTAS DESEADAS SI NINGUN NODO LO 
        # PRESELECCIONO
        self.mi_preseleccion = id_inge
        self.num_ack_preseleccion = len(self.nodos_activos)
        # ENVIAMOS A TODOS LOS NODOS NUESTRA PRESELECCION
        self.enviar_mensaje_activos(f"preseleccion {id_inge} {copy.copy(self.mi_indice)}")
        # ESPERAMOS RESPUESTA EN EL TIEMPO LIMITE
        tiempo_limite = time.time() + self.tolerancia_exclusion_ing
        while time.time() < tiempo_limite:
            time.sleep(0.5)
            # SI RECIBIMOS RESPUESTA, VA A REDUCIR EN UNO EL NUMERO, SI LLEGA A CERO NADIE
            # PRESELECCIONO A NUESTRO INGENIERO
            if self.num_ack_preseleccion == 0:
                return True
        return False

    # FUNCION PARA CERRAR TICKET [INGENIERO]
    def cerrar_ticket(self):
        try:
            # MOSTRAMOS LOS TICKETS ABIERTOS, GUARDAMOS SU ID Y PEDIMOS EL ID DEL TICKET A CERRAR
            self.cursor = self.conexion_bd.cursor()
            self.cursor.execute("SELECT * FROM Ticket WHERE estado = 'Abierto'")
            tickets_abiertos = self.cursor.fetchall()
            id_tickets_abiertos = [i[0] for i in tickets_abiertos]
            self.dar_formato(
                ["ID","FOLIO","DESCRIPCION","FECHA DE CREACION","ESTADO","DISPOSITIVO","INGENIERO"], tickets_abiertos)
            id_ticket = self.verificar_entrada(
                "Ingrese el id del ticket a Cerrar", int)
            # VERIFICAMOS QUE LA ENTRADA ESTE EN LOS TICKETS ABIERTOS
            while id_ticket not in id_tickets_abiertos:
                id_ticket = self.verificar_entrada(
                    "Ingrese un id valido del ticket a Cerrar", int)
            self.agregar_a_la_base(
                "UPDATE Ticket SET estado = %s WHERE  id = %s",('Cerrado',id_ticket))
        except mysql.connector.Error as err:
            self.db_error(err)
        finally:
            self.cursor.close()

    # OBTENEMOS EL ID DE LA SUCURSAL QUE TIENE ESE DISPOSITIVO
    def obtener_sucursal(self, id_dispo):
        for sucursal, dispositivos in enumerate(self.lista_distribucion):
            for id_dispositivo in dispositivos:
                if id_dispo == id_dispositivo:
                    return sucursal
        return -1

    # DEVOLVEMOS LA LISTA DE INGENIEROS LIBRES, INGENIEROS TOTALES = TODOS LOS INGENIEROS - INGENIEROS OCUPADOS - INGENIEROS PRESELECCIONADOS
    # EVITAMOS ASIGNAR EL MISMO INGENIERO DOS VECES
    def lista_ing_libres(self):
        try:
            self.cursor = self.conexion_bd.cursor()
            self.cursor.execute(
                "SELECT id_ingeniero FROM Ticket WHERE estado = 'Abierto'")
            ingenieros_ocupado = [id_inge[0] for id_inge in self.cursor.fetchall()]
            self.cursor.execute(
                "SELECT id FROM Ingenieros")
            todos_los_ingenieros = [id_inge[0] for id_inge in self.cursor.fetchall()]
            return set(todos_los_ingenieros) - set(ingenieros_ocupado) - set(self.inges_preseleccionados)
        except mysql.connector.errorcode as err:
            self.db_error(err)
        finally:
            self.cursor.close()
        
    # SI HAY INGENIEROS LIBRES REGRESAMOS VERDADERO
    def hay_ingeniero_libre(self):
        return True if len(self.lista_ing_libres()) else False

    # ASIGNAMOS A UN INGENIERO LIBRE
    def asignar_ingeniero(self):
        for ingeniero in self.lista_ing:
            if ingeniero[0] in self.lista_ing_libres():
                return ingeniero[0]
        return -1

    # PEDIMOS LOS DATOS PARA AGREGAR UN NUEVO DISPOSITIVO Y VERIFICAMOS LAS ENTRADAS   
    def agregar_dispositivo(self):
        nombre = input("Ingrese el nombre del dispositivo: ")
        modelo = input("Ingrese el modelo del dispositivo: ")
        ano_compra = self.verificar_entrada("Año de compra: ", int)
        mes = self.verificar_entrada("Mes de compra: ", int)
        dia = self.verificar_entrada("Día de compra: ", int)
        fecha = f"{ano_compra}-{mes}-{dia}"
        id_sucursal = self.sucursal_nuevo_dispo()
        # REALIZAMOS EL INSERT
        self.agregar_a_la_base(
            "INSERT INTO Dispos (nombre, modelo, fecha_compra, id_sucursal) VALUES (%s, %s, %s, %s)",
            (nombre, modelo, fecha, id_sucursal))
        # COMO AGREGAMOS NUEVO DISPOSITIVO, HAY QUE ASIGNARLO A UNA SUCURSAL
        

    # PEDIMOS LOS DATOS DEL NUEVO INGENIERO
    def agregar_ingeniero(self):
        nombre = input("Ingrese el nombre del ingeniero: ")
        apellido = input("Ingrese el apellido del ingeniero: ")
        self.agregar_a_la_base(
            "INSERT INTO Ingenieros (nombre, apellido) VALUES (%s, %s)",
            (nombre, apellido)
        )

    # PEDIMOS LOS DATOS DEL NUEVO USUARIO
    def agregar_usuario(self):
        nombre = input("Ingrese el nombre del usuario: ")
        correo = input("Ingrese el correo del usuario: ")
        self.agregar_a_la_base(
            "INSERT INTO User (nombre_usuario, correo_electronico) VALUES (%s, %s)",
            (nombre, correo)
        )

    # Obtenemos el id de la sucursal del nuevo dispositivo
    # EJ: Tenemos diez dispos en tres nodos
    # [[0,3,6,9],[1,4,7],[],[2,5,8]]
    # Buscamos el indice con menos
    def sucursal_nuevo_dispo(self):
        minimo = float('inf')
        indice_menos_dispos = -1
        for i, nodo in enumerate(self.lista_distribucion):
            if len(nodo):
                if len(nodo) < minimo:
                    minimo = len(nodo)
                    indice_menos_dispos = i

        return indice_menos_dispos

    # CREAMOS EL FORMATO PARA MOSTRAR LOS DATOS DE LA BASE DE DATOS COMO SI FUERAN UNA TABLA
    # EL ENCABEZADO CONTIENE LOS ENCABEZADOS DE CADA COLUMNA, Y LOS DATOS ES LA LISTA CON
    # LOS DATOS QUE QUEREMOS MOSTAR 
    def dar_formato(self, encabezado, datos):
        # OBTENEMOS EL ANCHO DEL ENCABEZAOD
        ancho_encabzado = [len(dato) for dato in encabezado]
        # RECORREMOS LOS DATOS PARA OBTENER LA MAYOR LONGITUD QUE EXISTE ENTRE LOS VALORES A MOSTRAR
        for dato in datos:
            for i, valor in enumerate(dato):
                valor_a_guardar = str(valor) if valor is not None else 'None'
                ancho_encabzado[i] = max(ancho_encabzado[i], len(valor_a_guardar))
        # ASIGNAMOS EL FORMATO, CADA COLUMNA SE VA A SEPARA POR '|', Y TENDRAN EL ESPACIO SUFICIENTE DE SEPARACION
        formato = ' | '.join([f"{{:<{ancho}}}" for ancho in ancho_encabzado])
        encabezado_a_imprimir = formato.format(*encabezado)

        # IMPRIMIMOS EL ENCABEZADO
        print(encabezado_a_imprimir)
        print('-'*len(encabezado_a_imprimir))

        # RECORREMOS LOS DATOS PARA ASIGNARLES EL MISMO FORMATO Y LOS IMPRIMIMOS
        for dato in datos:
            fila = [str(valor) if valor is not None else 'None' for valor in dato]
            print(formato.format(*fila))

    # MOSTRAMOS LOS DISPOSITIVOS DE LA BASE DE DATOS, CON EL FORMATO ASIGNADO
    def mostrar_dispos(self):
        self.dar_formato(
            ["ID", "NOMBRE", "MODELO", "FECHA DE COMPRA","SUCURSAL"], self.lista_dispos)
    
    # MOSTRAMOS LOS INGENIEROS DE LA BASE DE DATOS, CON EL FORMATO ASIGNADO  
    def mostrar_inges(self):
        self.dar_formato(
            ["ID","NOMBRE", "APELLIDO"], self.lista_ing)

    # MOSTRAMOS LOS USUARIOS DE LA BASE DE DATOS, CON EL FORMATO ASIGNADO
    def mostrar_usuarios(self):
        self.dar_formato(
            ["ID", "NOMBRE", "CORREO"],self.lista_users)

    # MOSTRAMOS LOS TICKETS DE LA BASE DE DATOS, CON EL FORMATO ASIGNADO
    def mostrar_tickets(self):
        self.dar_formato(
            ["ID","FOLIO","DESCRIPCION","FECHA DE CREACION","ESTADO","DISPOSITIVO","INGENIERO"],self.lista_tickets)

    # ACTUALIZAMOS ALGUN DATO DE ALGUN DISPOSITIVO
    def actualizar_dispo(self):
        # MOSTRAMOS LOS DISPOSITIVOS QUE TENEMOS EN LA BASE DE DATOS
        self.mostrar_dispos()
        # OBTENEMOS EL ID DEL DISPOSITIVO
        id_dispo = self.verificar_entrada(f"Ingrese el id del dispositivo",int)
        # VERIFICAMOS QUE SEA VALIDO
        while(id_dispo > len(self.lista_dispos)):
            id_dispo = self.verificar_entrada(f"Ingrese el id valido del dispositivo",int)
        # OBTENEMOS EL CAMPO A ACTUALIZAR
        accion = self.verificar_entrada(
            "Que desea actualizar?: \n\t 1.Nombre\n\t2.Modelo\n\t3.Fecha de compra\n\t",int)
        # REALIZAMOS LA ACTUALIZACION REQUERIDA
        if accion == 1:
            nuevo_nombre = input("Ingrese el nuevo nombre: ")
            self.agregar_a_la_base(
                "UPDATE Dispos SET nombre = %s WHERE  id = %s",(nuevo_nombre,id_dispo))
        elif accion == 2:
            nuevo_modelo = input("Ingrese el nuevo modelo: ")
            self.agregar_a_la_base(
                "UPDATE Dispos SET modelo = %s WHERE  id = %s",(nuevo_modelo,id_dispo))
        elif accion == 3:
            nuevo_ano_compra = self.verificar_entrada("Año de compra: ", int)
            nuevo_mes = self.verificar_entrada("Mes de compra: ", int)
            nuevo_dia = self.verificar_entrada("Día de compra: ", int)
            nueva_fecha = f"{ano_compra}-{mes}-{dia}"
            self.agregar_a_la_base(
                "UPDATE Dispos SET fecha_compra = %s WHERE  id = %s",(nueva_fecha,id_dispo))
        else:
            print("Opción no válida")

    # actualizamos algun dato de algun ingeniero
    def actualizar_ingeniero(self):
        # MOSTRAMOS LOS INGENIEROS QUE TENEMOS, PEDIMOS Y VERIFICAMOS SU ID, Y EL CAMPO QUE QUEREMOS 
        # ACTUALIZAR, Y PEDIMOS LOS NUEVOS DATOS PARA HACER LE UPDATE
        self.mostrar_inges()
        id_inge = self.verificar_entrada(f"Ingrese el id del ingeniero",int)
        while(id_inge > len(self.lista_ing)):
            id_inge = self.verificar_entrada(f"Ingrese el id valido para el ingeniero",int)
        accion = self.verificar_entrada(
            "Que desea actualizar?: \n\t 1.Nombre\n\t2.apellido\n\t",int)
        if accion == 1:
            nuevo_nombre = input("Ingrese el nuevo nombre: ")
            self.agregar_a_la_base(
                "UPDATE Ingenieros SET nombre = %s WHERE  id = %s",(nuevo_nombre,id_inge))
        elif accion == 2:
            nuevo_apellido = input("Ingrese el nuevo apellido: ")
            self.agregar_a_la_base(
                "UPDATE Ingenieros SET apellido = %s WHERE  id = %s",(nuevo_apellido,id_inge))
        else:
            print("Opción no válida")

    # actualizamos algun dato de algun usuario
    def actualizar_usuario(self):
        # MOSTRAMOS LOS USUARIOS QUE TENEMOS, PEDIMOS Y VERIFICAMOS SU ID, Y EL CAMPO QUE QUEREMOS 
        # ACTUALIZAR, Y PEDIMOS LOS NUEVOS DATOS PARA HACER LE UPDATE
        self.mostrar_usuarios()
        id_usuario = self.verificar_entrada(f"Ingrese el id del usuario",int)
        while(id_usuario > len(self.lista_users)):
            id_usuario = self.verificar_entrada(f"Ingrese el id valido para el usuario",int)
        accion = self.verificar_entrada(
            "Que desea actualizar?: \n\t 1.Nombre\n\t2.Correo Electronico\n\t",int)
        if accion == 1:
            nuevo_nombre = input("Ingrese el nuevo nombre: ")
            self.agregar_a_la_base(
                "UPDATE User SET nombre = %s WHERE  id = %s",(nuevo_nombre,id_usuario))
        elif accion == 2:
            nuevo_correo = input("Ingrese el nuevo Correo: ")
            self.agregar_a_la_base(
                "UPDATE User SET correo_electronico = %s WHERE  id = %s",(nuevo_correo,id_usuario))
        else:
            print("Opción no válida")

    # GUARDAMOS LOS MENSAJES EN EL ARCHIVO LOG CON EL FORMATO ESTABLECIDO Y SI ES UN MENSAJE RECIBIDO O ENVIADO
    def log(self, mensaje, nodo_origen, tipo_mensaje, timestamp):
        with open(self.log_file, "a") as file:
            file.write(f"{mensaje}\t\t{nodo_origen}\t\t{tipo_mensaje}\t\t{timestamp}\n")

    # ENVIAMOS ALGUN MENSAJE AL NODO DESTINO, CON SU CORRESPONDIENTE TIMESTAMP
    def send(self, indice_destino, mensaje):
        try:
            nodo_destino = self.nodos[indice_destino]
            timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S:%f")[:-3]
            mensaje_a_enviar = f"{mensaje} {timestamp}"
            self.socket.sendto(mensaje_a_enviar.encode("utf-8"), (nodo_destino["ip"], nodo_destino["port"]))
            self.log(mensaje, nodo_destino["ip"], "enviado", timestamp)
        except OSError as e:
            print(f"Error: {e}")

    # AGREGAMOS ALGUN NUEVO NODO ACTIVO, COMPARAMOS SI NO EXISTE YA EN LA LISTA DE NODOS ACTIVOS
    def agregar_nodo_activo(self, nodo):
        if nodo not in self.nodos_activos:
            self.nodos_activos.append(nodo)

    # CUANDO TENEMOS CONOCIMIENTO DE UN NUEVO NODO, OBTENEMOS SU INDICE Y LE DAMOS A CONOCER QUE NOS ENCONTRAMOS 
    # ACTVOS, LO AGREGAMOS A LA LISTA DE NODOS ACTIVOS Y EN CASO DE QUE SU INDICE SEA MAYOR QUE EL NUESTRO, LE 
    # DAMOS EL CONTROL DE NODO MAESTRO, SI NO, LE DAMOS A CONOCER QUE SOMOS EL NODO MAESTRO
    def nuevo_nodo(self, mensaje):
        nodo = int(re.search(r'\d+', mensaje).group())
        self.send(nodo, f"estoy_activo {copy.copy(self.mi_indice)}")
        self.agregar_nodo_activo(nodo)
        if self.soy_maestro:
            if nodo > copy.copy(self.mi_indice):
                self.send(nodo, f"cedo_maestro {copy.copy(self.mi_indice)}")
            else:
                self.send(nodo, f"coordinador {copy.copy(self.mi_indice)}")
                self.iniciar_distribucion()
        # ACTUALIZAMOS SU HEARTBEAT PORQUE TENEMOS CONOCIMIENTO DE SU EXISTENCIA
        self.actualizar_heartbeat(mensaje)

    # MANDAMOS MENSAJE A TODOS LOS NODOS DE QUE ESTAMOS VIVOS CADA TIEMPO DE ESPERA
    def heartbeat(self):
        while True:
            self.enviar_mensaje_activos(f"heartbeat {copy.copy(self.mi_indice)}")
            time.sleep(self.espera_heartbeat)

    # SI SOMOS COORDINADORES CAMBIAMOS LAS BANDERAS PARA QUE NOS DEMOS CUENTA
    def soy_coordinador(self):
        self.soy_maestro = True
        self.nodo_maestro = copy.copy(copy.copy(self.mi_indice))
        self.hay_eleccion = False

    # ENVIAMOS MENSAJE A TODOS LOS DEMAS NODOS (EXCEPTO A NOSOTROS)
    def enviar_mensaje_activos(self, mensaje):
        for i in self.nodos_activos:
                self.send(i, mensaje)

    # VERIFICAMOS LA ACTIVIDAD DE LOS NODOS SEGUN SU HEARBEAT Y LA TOLERANCIA ASIGNADA
    def verificar_nodos_activos(self):
        while True:
            # SI NO HAY NODOS ACTIVOS, SOMOS EL COORDINADOR Y NO HAY NECESIDAD DE VERIFICAR LOS DEMAS NODOS
            # HASTA QUE SE CONOZACA LA EXISTENCIA DE UN NODO NUVEO
            if not len(self.nodos_activos):
                self.soy_coordinador()
                self.iniciar_distribucion()
            else:
                # SI NO SOMOS EL UNICO NODO ACTIVO, COMPARAMOS EL TIEMPO ACTUAL CON EL ULTIMO HEARTBEAT QUE SE TIENE
                # DE CADA NODO ACTIVO, Y SI EXCEDE LA TOLERANCIA, LO BORRAMOS DE LISTA, REALIZAMOS EL PROCESO DE ELECCION
                # SI CAE EL NODO MAESTRO Y SI NO, REALIZAMOS DISTRIBUCION SI ES QUE SOMOS COORDINADORES
                for i in range(len(self.nodos)):
                    if i != copy.copy(self.mi_indice):
                        if time.time() - self.ultimo_heartbeat[i] > self.tolerancia_heartbeat:
                            self.elegir_coordinador_si_esta_muerto()
                            if i in self.nodos_activos:
                                self.nodos_activos.remove(i)
                                self.iniciar_redistribucion(i) if self.soy_maestro else self.enviar_mensaje_activos(f"redistribucion {i}")
                        else:
                            self.agregar_nodo_activo(i)
            time.sleep(self.tiempo_verificacion_heartbeat)

    # VERIFICAMOS CADA CIERTO TIEMPO SI HAY ELECCION, UTILIZANDO DE BASE EL ALGORITMO DEL BULLY
    def verificar_eleccion(self):
        while True:
            # SI HAY ELECCION Y NO HA HABIDO RESPUESTA DE OTRO NODO CON INDICE SUPERIOR, SOMOS EL NODO MAESTRO
            # CAMBIAMOS LAS BANDERAS CORRESPONDIENTES Y AVISAMOS A LOS DEMAS NODOD
            if self.hay_eleccion and not self.ack_eleccion:
                if time.time() - self.tiempo_eleccion > self.espera_ack_eleccion:
                    self.soy_coordinador()
                    self.enviar_mensaje_activos(f"coordinador {copy.copy(self.mi_indice)}")
                    self.hay_eleccion = False
            time.sleep(self.tiempo_espera_eleccion)

    # ACTUALIZAMOS EL VALOR DEL TIEMPO DEL ULTIMO HEARTBEAT EN LA LISTA EN SU LUGAR CORRESPONDIENTE
    def actualizar_heartbeat(self, mensaje):
        nodo = int(re.search(r'\d+', mensaje).group())
        if nodo != copy.copy(self.mi_indice):
            self.ultimo_heartbeat[nodo] = time.time()

    # SI HAY UN NUEVO NODO MAESTRO, CAMBIAMOS LAS BANDERA CORRESPONDIENTES
    def nuevo_maestro(self, mensaje):
        # GUARDAMOS EL PRIMERO NUMERO QUE ENCONTREMOS EN EL MENSAJE, EL CUAL ES EL INDICE DEL NODO
        nodo = int(re.search(r'\d+', mensaje).group())
        self.nodo_maestro = nodo
        self.soy_maestro = nodo == copy.copy(self.mi_indice)
        self.hay_eleccion = False
        self.ack_eleccion = False
    
    # ASIGNAMOS EL TIEMPO DE INICIO DE LA ELECCION, CAMBIAMOS LAS BANDERA Y ENVIAMOS EL PROCESO A LOS NODOS SUPERIORES
    def iniciar_eleccion(self):
        self.tiempo_eleccion = time.time()
        self.hay_eleccion = True
        for i in range (copy.copy(self.mi_indice) + 1 , len(self.nodos) -1 ):
            self.send(i, f"eleccion {copy.copy(self.mi_indice)}")

    # SI EL NODO MAESTRO NO ESTA EN LOS NODOS ACTIVOS Y AUN NO SE SABE QUE HAY ELECCION, INICIAMOS EL PROCESO
    def elegir_coordinador_si_esta_muerto(self):
        if self.nodo_maestro not in self.nodos_activos and not self.hay_eleccion:
            self.iniciar_eleccion()

    # CERRAMOS LO QUE SEA NECESARIO, RECORDEMOS QUE ES LENGUAJE INTERPRETADO, POR LO QUE AL CERRAR EL PROGRMA O APAGAR LA COMPUTADORA
    # LOS RECURSOS REGRESAN AL SISTEMA OPERATIVO
    def close(self):
        self.socket.close()
        sys.exit()

    # AL LEVANTAR EL NODO AVISMOS A TODOS QUE ACABAMOS DE INICIAR OPERACIONES
    def raising(self):
        for i in range(len(self.nodos)):
            if i != copy.copy(self.mi_indice):
                self.send(i, f"raise {copy.copy(self.mi_indice)}")

    # AL REALIZAR DISTRIBUCION O REDISTRIBUCION LAS REPARTICION DE LOS DISPOSITIVOS CAMBIA, 
    # POR LO QUE HAY QUE ACTUALIZAR SU INFORMACION
    def actualizar_sucursal_dispos(self):
        for sucursal,dispositivos in enumerate(self.lista_distribucion):
            for id_dispo in dispositivos:
                try: 
                    self.agregar_a_la_base(
                        "UPDATE Dispos SET id_sucursal = %s WHERE id = %s",(sucursal+1,id_dispo ))
                except mysql.connector.errorcode as err:
                    self.db_error(err)

    # INICIAMOS EL PROCESO DE DISTRIBUCION, SI ES QUE SOMOS EL NODO MAESTRO
    def iniciar_distribucion(self):
        if self.soy_maestro:
            # LIMPIAMOS LAS LISTAS DE DISPOSITIVOS
            self.lista_distribucion = [[] for i in range(len(self.nodos))]
            self.mis_dispositivos = []
            # SI SOMOS EL UNICO NODO ACTIVO, NOS ASIGNAMOS TODOS LOS DISPOSITIVOS, ACTUALIZAMOS LA LISTA DE DISTRIBUCION
            # Y LO CARGAMOS A LA BASE DE DATOS
            if len(self.nodos_activos) == 0:
                self.mis_dispositivos = [dispo[0] for dispo in self.lista_dispos]
                self.lista_distribucion[copy.copy(self.mi_indice)] = self.mis_dispositivos
                self.actualizar_sucursal_dispos()
            else:
                # SI NO SOMOS EL UNICO NODO EN EL SISTEMA, ADQUIRIMOS LOS NODOS QUE SE ENCUENTRAN ACTIVOS
                # LOS RECORREMOS Y DEPENDIENDO DEL INDICE Y SU MODULO LE ASIGNAMOS UN DISPOSITIVO, ESTO
                # PARA QUE SE DISTRIBUYA DE MANERA UNIFORME
                # EJ:
                # INDICES = [0, 3]
                # DISPOSITIVOS = [0,1,2,3,4,5,6,7,8]
                # SEGUN EL MODULO
                # LISTA_DISTRIBUCION = [[0,2,4,6,8],[],[],[1,3,5,7]]
                indices = self.nodos_activos.copy()
                indices.append(copy.copy(self.mi_indice))
                for indice, dispo in enumerate(self.lista_dispos):
                    self.lista_distribucion[indices[indice%len(indices)]].append(dispo[0])
                # ACTUALIZAMOS LA INFORMACION EN LAS LISTAS, EN LA BASE DE DATOS Y MANDAMOS A LOS DEMAS 
                # NODOS LA NUEVA DISTRIBUCIO
                self.mis_dispositivos = self.lista_distribucion[copy.copy(self.mi_indice)]
                self.actualizar_sucursal_dispos()
                self.enviar_mensaje_activos(f"distribucion {self.lista_distribucion}")                

    # SI UN NODO CAE, REALIZAMOS LA REDISTRIBUCION DE LOS DISPOSITIVOS, SI ES QUE SOMOS NODO MAESTRO
    def iniciar_redistribucion(self,nodo_vacio):
        if self.soy_maestro:
            # SI SOMOS EL UNICO NODO ACTIVO, NOS ASIGNAMOS TODOS LOS DISPOSITIVOS, ACTUALIZAMOS LA LISTA DE DISTRIBUCION
            # Y LO CARGAMOS A LA BASE DE DATOS
            if len(self.nodos_activos) == 0:
                self.mis_dispositivos = [dispo[0] for dispo in self.lista_dispos]
                self.lista_distribucion[copy.copy(self.mi_indice)] = self.mis_dispositivos
                self.actualizar_sucursal_dispos()
            else:
                # SI NO SOMOS LOS UNICOS ACTIVOS, OBTENEMOS LA LISTA DE DISPOSITIVOS A DISTRIBUIR
                # VACIAMOS EL LUGAR DEL NODO QUE CAYO Y RECORREMOS LA LISTA DE DISTRIBUCION NODO POR NODO Y LE ASIGNAMOS
                # UN NUEVO DISPOSITIVO SEGUN SU MODULO
                # EJ:
                # LISTA_DISTRIBUCION_ANTERIOR = [[0,3,],[1,4],[],[2,5]]
                # LISTA_DISTRIBUCION_NUEVA = [[0,3,5],[1,4,2],[],[]]
                elementos_a_repartir = self.lista_distribucion[nodo_vacio].copy()
                self.lista_distribucion[nodo_vacio] = []
                indices = self.nodos_activos.copy()
                indices.append(copy.copy(self.mi_indice))
                for i, dispo in enumerate(elementos_a_repartir):
                    indice = indices[i%len(indices)]
                    self.lista_distribucion[indice].append(dispo)
                # ACTUALIZAMOS LAS LISTAS Y LA BASE DE DATOS Y LE DAMOS A CONOCER LA NUEVA DISTRIBUCION A LOS
                # DEMAS NODOS
                self.mis_dispositivos = self.lista_distribucion[copy.copy(self.mi_indice)]
                self.actualizar_sucursal_dispos()
                self.enviar_mensaje_activos(f"distribucion {self.lista_distribucion}")
        else:
            # SI NO SOMOS EL NODOS MAESTRO Y NOS ENTERAMOS DE LA EXISTENCIA DEL NODO CAIDO, AVISAMOS A LOS DEMAS NODOS
            self.enviar_mensaje_activos(f"redistribucion {nodo_vacio}")

    # RECIBIMOS LOS MENSAJES DE LOS NODOS
    def receive(self):
        while True:
            try:
                # GUARDAMOS EL MENSAJE EN ARCHIVO LOG
                mensaje_recibido, nodo_origen = self.socket.recvfrom(1024)
                timestamp = datetime.now().strftime("%Y/%m/%d %H:%M:%S:%f")[:-3]
                self.log(f"{mensaje_recibido}", nodo_origen[0], "recibido", timestamp)
                # DESCOMPONEMOS EL MENSAJE PARA REALIZAR ALGUNA ACCION SEGUN EL MENSAJE
                self.obtener_mensaje(mensaje_recibido.decode('utf-8'))
            except ConnectionResetError:
                print("Conexión perdida")
                break
            except OSError as e:
                print(f"Error: {e}")
                break
   
    # ANALIZAMOS EL MENSAJE RECIBIDO DEL NODO Y REALIZAMOS ALGUNA ACCION CON EL
    # ES IMPORTANTE EL ORDEN EN QUE ACOMODAMOS LOS IF, PORQUE EL PARAMETRO IN RECONOCE SUBCADENAS
    # POR ESO DEBE IR ANTES 'ACK_ELECCION' QUE 'ELECCION', O 'REDISTRIBUCION' QUE 'DISTRIBUCION'
    def obtener_mensaje(self, mensaje):
        if "heartbeat" in mensaje:
            # ACTUALIZAMOS EL ULTIMO HEARBEAT DEL NODO, USADO PARA VERIFICAR SI CAYO ALGUN NODO
            self.actualizar_heartbeat(mensaje)
        elif "raise" in mensaje:
            # UN NUEVO NODO HA DESPERTADO, ASI QUE LO GUARDAMOS Y LE DAMOS A CONOCER NUESTRA EXISTENCIA, Y/O EL CONOCIMIENTO
            # DEL NODO MAESTRO
            self.nuevo_nodo(mensaje)
        elif "cedo_maestro" in mensaje:
            # NOS CEDIERON EL CONTROL DE NODO MAESTRO, CAMBIAMOS LAS BANDERAS Y LES AVISAMOS A LOS DEMAS NODOS QUE AHORA
            # SOMO NOSOTROS, INICIAMOS LA DISTRIBUCION DE LOS DISPOSITIVOS
            self.soy_coordinador()
            self.enviar_mensaje_activos(f"coordinador {copy.copy(self.mi_indice)}")
            self.iniciar_distribucion()
        elif "commit" in mensaje:
            with self.bd_lock:
                self.query_distribuida = str(mensaje)
                self.comenzar_hilo()
        elif "estoy_activo" in mensaje:
            # ACABAMOS DE ACITVARNOS Y NOS AVISARON DE LA EXISTENCIA DE UN NODO ACTIVO, HAY QUE AGREGARLO A 
            # LA LISTA DE NODOS ACITVOS
            nodo = int(re.search(r'\d+', mensaje).group())
            self.agregar_nodo_activo(nodo)
        elif "coordinador" in mensaje:
            # SE HA TERMINADO EL PROCESO DE ELECCION, POR LO QUE HAY QUE GUARDAR LA INFORMACION DEL 
            # NUEVO NODO MAESTRO
            self.nuevo_maestro(mensaje)
        # LIBERAMOS EL INDICE DEL INGENIERO PRESELECCIONADO
        elif "liberar_preseleccion" in mensaje:
            nodo = int(re.search(r'\d+', mensaje).group())
            self.inges_preseleccionados().remove(nodo)
        # SI TENEMOS ACK, LIBERAMOS UN NODO DE LA ESPERA
        elif "ack_preseleccion" in mensaje:
            self.num_ack_preseleccion = self.num_ack_preseleccion - 1
        # VERIFICAMOS QUE NO HAYAMOS PRESELECCIONADO AL INGENIERO, SI NO, LE ENVIAMOS
        # RESPUESTA Y GUARDAMOS SU PRESELECCION PARA NO TOMARLA EN CUENTA SI QUEREMOS LEVANTAR TICKETS
        elif "preseleccion" in mensaje:
            nodos = re.findall(r'\d+', mensaje)
            if int(nodos[0]) != self.mi_preseleccion:
                self.send(int(nodos[1]), f"ack_preseleccion {copy.copy(self.mi_indice)} ")
                self.inges_preseleccionados.append(int(nodos[0]))
        elif "ack_eleccion" in mensaje:
            # SI RECIBIMOS CONFIRMACION DE UN NODO CON INDICE MAYOR EN EL PROCESO DE ELECCION,
            # DAMOS POR TERMINADO NUESTRO PROCESO
            self.ack_eleccion = True
        elif "eleccion" in mensaje:
            # EL NODO MAESTRO HA CAIDO POR LO QUE INICIAMOS EL PROCESO DE ELECCION, ENVIAMOS
            # ENTERADO AL NODO ANTERIOR PARA QUE TERMINE SU ELECCION E INICIAMOS LA NUESTRA
            nodo = int(re.search(r'\d+', mensaje).group())
            self.send(nodo, f"ack_eleccion {copy.copy(self.mi_indice)}")
            self.iniciar_eleccion()
        elif "redistribucion" in mensaje:
            # NOS HA LLEGADO MENSAJE DE QUE CAYO EL NODO MAESTRO Y HAY QUE REALIAZAR REDISTRIBUCION
            # SI SOMO EL NODO MAESTRO NOS INTERESA, SI NO, SE DESCARTA
            nodo_caido = int(re.search(r'\d+', mensaje).group())
            self.hay_redistribucion = True
            self.iniciar_redistribucion(nodo_caido)
        elif "distribucion" in mensaje:
            # NOS HAN ENVIADO LA NUEVA LISTA DE DISTRIBUCION, SEPARAMOS LOS DATOS QUE NOS INTERESAN Y
            # LOS GUARDAMOS EN LA LISTA DE DISTRIBUCION, ACTUALIZAMOS NUESTROS DISPOSITIVOS Y LA BASE DE DATOS
            # LEEMOS LA LISTA DE DISTRIBUCION CON EXPRESIONES REGULARE,
            # NOS INTERESAN LOS DATOS QUE SE ENCUENTREN EN LOS CORCHETES [[],[],[],[]]
            self.hay_redistribucion = False
            obtener_lista = re.search(r"\[\[.*?\]\]", mensaje)
            self.lista_distribucion = ast.literal_eval(obtener_lista.group())
            self.mis_dispositivos = self.lista_distribucion[copy.copy(self.mi_indice)]
            self.actualizar_sucursal_dispos()
    



if __name__ == "__main__":
    indice_host = int(input("Ingrese el índice del host: "))
    ticket = Tickets(indice_host)
