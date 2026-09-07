
module modbus;

import std::io;

def ModbusError = enum { OK, TIMEOUT, CRC, CONN };

struct ModbusClient {
    char* ip;
    int port;
    int socket_fd;
}

fn ModbusClient.connect(self) ModbusError! {
    // тут реальный TCP connect на C уровне - без GC, детерминировано
    io::printn("Connecting to {self.ip}:{self.port}");
    return ModbusError.OK;
}

fn ModbusClient.read_holding(self, int addr, int count) float! {
    // Чтение 40001 - обработка big-endian сразу тут
    // defer close socket и т.д.
    if (count <=0) return 0.0;
    // мок
    return 23.5;
}

fn modbus_read(char* ip, int port, int reg) float @extern("modbus_read") {
    ModbusClient c = { .ip = ip, .port = port, .socket_fd = -1 };
    c.connect()!!;
    return c.read_holding(reg, 1)!!;
}
