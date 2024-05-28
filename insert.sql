INSERT INTO Sucursal ( nombre, direccion) VALUES ('DistribuidosTech','Explanada Cristina Valencia 42 - Tulsa, Bal / 62159');
INSERT INTO Sucursal ( nombre, direccion) VALUES ('SistemasCloud','Barranco Germán, 1 - Birmingham, Ara / 32909');
INSERT INTO Sucursal ( nombre, direccion) VALUES ('DistribuidosSolutions','Conjunto Homero, 32 - Levittown, Mad / 27416');
INSERT INTO Sucursal ( nombre, direccion) VALUES ('CloudDistribuidos','Explanada Marta 89 - Bartlett, Mur / 14912');

INSERT INTO User (nombre_usuario, correo_electronico) VALUES('Alejandro García','ale.garcia90@example.com');
INSERT INTO User (nombre_usuario, correo_electronico) VALUES('Adriana López','adriana.lopez.mex@example.com');
INSERT INTO User (nombre_usuario, correo_electronico) VALUES('Carlos Hernández','carlos.hdez.85@example.com');
INSERT INTO User (nombre_usuario, correo_electronico) VALUES('María Rodríguez','maria.rodriguez.mx@example.com');

INSERT INTO Ingenieros (nombre, apellido) VALUES ('Javier','Sanchez');
INSERT INTO Ingenieros (nombre, apellido) VALUES ('Luis','Vargas');
INSERT INTO Ingenieros (nombre, apellido) VALUES ('Ana','Torres');
INSERT INTO Ingenieros (nombre, apellido) VALUES ('Andrea','Matinez');


INSERT INTO Dispos (nombre, modelo, fecha_compra, id_sucursal) VALUES ('Smartphone','TechX 2000','2023-08-15',NULL);
INSERT INTO Dispos (nombre, modelo, fecha_compra, id_sucursal) VALUES ('Laptop','QuantumBook Pro',' 2022-11-30',NULL);
INSERT INTO Dispos (nombre, modelo, fecha_compra, id_sucursal) VALUES ('Smartwatch','FitLife 500','2024-04-05',NULL);
INSERT INTO Dispos (nombre, modelo, fecha_compra, id_sucursal) VALUES ('Tablet','HyperTab X10','2023-05-20',NULL);

INSERT INTO Ticket (folio, descripcion, fecha_creacion, estado, id_dispositivo, id_ingeniero) VALUES ('1-2-2-1','Pantalla rota','2023-07-18 09:30:00', 'Cerrado', 1, 2);
INSERT INTO Ticket (folio, descripcion, fecha_creacion, estado, id_dispositivo, id_ingeniero) VALUES ('4-1-1-2','Correa suelta','2024-03-12 15:45:00', 'Abierto', 3, 1);
INSERT INTO Ticket (folio, descripcion, fecha_creacion, estado, id_dispositivo, id_ingeniero) VALUES ('2-3-4-3','Pantalla rota','2022-11-25 11:00:00', 'Abierto', 1, 2);