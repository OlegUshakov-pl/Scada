
module modbus_driver;
import std::io;
import std::time;

// C bindings
extern fn void* modbus_new_tcp(char* ip, int port);
extern fn int modbus_connect(void* ctx);
extern fn int modbus_read_registers(void* ctx, int addr, int nb, ushort* dest);
extern fn void modbus_close(void* ctx);
extern fn void modbus_free(void* ctx);
extern fn char* modbus_strerror(int errnum);

extern fn void* redisConnect(char* ip, int port);
extern fn void* redisCommand(void* c, char* format, ...);
extern fn int redisGetError(void* c);
extern fn char* redisGetErrorStr(void* c);

const int MODBUS_ADDR = 0;
const int MODBUS_NB = 10; // читаем 10 регистров
const char* MODBUS_IP = "192.168.1.10"; // поменяй на IP ПЛК
const char* REDIS_IP = "127.0.0.1";

fn void main()
{
    io::printn("=== C3 Modbus -> Redis Driver ===");
    io::printn("Подключаюсь к Modbus %s:502", MODBUS_IP);
    io::printn("И к Redis %s:6379", REDIS_IP);

    void* modbus_ctx = modbus_new_tcp((char*)MODBUS_IP, 502);
    if (modbus_ctx == null)
    {
        io::printn("Ошибка создания modbus ctx");
        return;
    }

    if (modbus_connect(modbus_ctx) == -1)
    {
        io::printn("Modbus connect failed");
        modbus_free(modbus_ctx);
        return;
    }
    io::printn("Modbus подключен!");

    void* redis_ctx = redisConnect((char*)REDIS_IP, 6379);
    if (redis_ctx == null || redisGetError(redis_ctx) != 0)
    {
        io::printn("Redis connect failed: %s", redisGetErrorStr(redis_ctx));
        modbus_close(modbus_ctx);
        modbus_free(modbus_ctx);
        return;
    }
    io::printn("Redis подключен!");

    ushort[10] regs;
    int cycle = 0;

    while (true)
    {
        int rc = modbus_read_registers(modbus_ctx, MODBUS_ADDR, MODBUS_NB, &regs[0]);
        if (rc != MODBUS_NB)
        {
            io::printn("Read failed cycle %d", cycle);
            time::sleep(500 * time::MS);
            // попробуй переподключиться
            modbus_close(modbus_ctx);
            modbus_connect(modbus_ctx);
            continue;
        }

        // Предположим карта:
        // reg 0 = pressure *10 (15 = 1.5 бар)
        // reg 1 = temp_01 *10
        // reg 2 = pump_01 feedback
        float pressure = regs[0] / 10.0;
        float temp_01 = regs[1] / 10.0;

        // Пишем в Redis для FastAPI и Logic Engine
        // HSET latest_tags pressure 1.5 temp_01 85.0
        redisCommand(redis_ctx, "HSET latest_tags pressure %f temp_01 %f pump_fb %d", pressure, temp_01, regs[2]);

        // Также проверяем команды обратно от Logic Engine
        // HGET commands pump_01
        // Если есть команда, пишем в ПЛК
        // void* reply = redisCommand(redis_ctx, "HGET commands pump_01");
        // if (reply) -> modbus_write_register(ctx, 10, value)

        if (cycle % 20 == 0) // лог каждые 2 сек
        {
            io::printn("[%d] pressure=%.1f bar temp=%.1f C fb=%d", cycle, pressure, temp_01, regs[2]);
        }

        cycle++;
        time::sleep(100 * time::MS); // 10 Гц опрос
    }

    modbus_close(modbus_ctx);
    modbus_free(modbus_ctx);
}
