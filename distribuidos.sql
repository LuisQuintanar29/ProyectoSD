CREATE DATABASE IF NOT EXISTS Distribuidos;

-- Usar la base de datos recién creada
USE Distribuidos;

-- Tabla Ingenieros
CREATE TABLE IF NOT EXISTS Ingenieros (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(50),
    apellido VARCHAR(50)
);

-- Tabla User
CREATE TABLE IF NOT EXISTS User (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre_usuario VARCHAR(50),
    correo_electronico VARCHAR(100)
);

-- Tabla Sucursal
CREATE TABLE IF NOT EXISTS Sucursal (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100),
    direccion VARCHAR(255)
);

-- Tabla Dispos
CREATE TABLE IF NOT EXISTS Dispos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100),
    modelo VARCHAR(50),
    fecha_compra DATE,
    id_sucursal INT,
    FOREIGN KEY (id_sucursal) REFERENCES Sucursal(id)
);

-- Tabla Ticket
CREATE TABLE IF NOT EXISTS Ticket (
    id INT AUTO_INCREMENT PRIMARY KEY,
    folio VARCHAR(255) NOT NULL,
    descripcion TEXT,
    fecha_creacion DATETIME,
    estado ENUM('Abierto', 'Cerrado'),
    id_dispositivo INT,
    id_ingeniero INT,
    FOREIGN KEY (id_dispositivo) REFERENCES Dispos(id),
    FOREIGN KEY (id_ingeniero) REFERENCES Ingenieros(id)
);
