
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

// libc для чтения конфига (простой формат "name,address" построчно)
extern fn void* fopen(char* path, char* mode);
extern fn char* fgets(char* s, int size, void* stream);
extern fn int fclose(void* stream);
extern fn int sscanf(char* str, char* fmt, ...);
extern fn void* memset(void* s, int c, usz n);
extern fn usz strlen(char* s);

const char* MODBUS_IP = "192.168.1.10"; // поменяй на IP ПЛК
const char* REDIS_IP = "127.0.0.1";
// Конфиг экспортируется из Django:
//   python manage.py export_device_config 1 --out /config/device_1.txt
// Формат: по строке "name,address", например:
//   pressure,0
//   temp_01,1
//   pump_fb,2
const char* CONFIG_PATH = "/config/device_1.txt";
const int MAX_TAGS = 64;
const int MAX_REGS = 125; // лимит одного Modbus-чтения

struct TagMap
{
    char[64] name;
    int address;
}

TagMap[64] TAGS;

// Читает конфиг "name,address" построчно. Возвращает число тэгов (0 = ошибка/пусто).
fn int load_config(char* path, TagMap* tags, int max_tags)
{
    void* f = fopen(path, "r");
    if (f == null)
    {
        io::printn("Конфиг не найден: %s", path);
        return 0;
    }
    char[128] line;
    int count = 0;
    while (fgets(&line[0], 128, f) != null)
    {
        if (count >= max_tags) break;
        if (line[0] == '#' || line[0] == '\n' || line[0] == '\0') continue;
        char[64] name;
        int addr = -1;
        memset(&name[0], 0, 64);
        // формат: name,address
        if (sscanf(&line[0], "%63[^,],%d", &name[0], &addr) != 2) continue;
        if (addr < 0) continue;
        memset(&tags[count].name[0], 0, 64);
        // копируем имя (до \0)
        usz n = strlen(&name[0]);
        if (n > 63) n = 63;
        for (usz i = 0; i < n; i++) tags[count].name[i] = name[i];
        tags[count].address = addr;
        count++;
    }
    fclose(f);
    io::printn("Загружено тэгов из %s: %d", path, count);
    for (int i = 0; i < count; i++)
    {
        io::printn("  %s -> reg %d", &tags[i].name[0], tags[i].address);
    }
    return count;
}

fn void main()
{
    io::printn("=== C3 Modbus -> Redis Driver (config-driven) ===");
    io::printn("Конфиг: %s", CONFIG_PATH);
    io::printn("Подключаюсь к Modbus %s:502", MODBUS_IP);
    io::printn("И к Redis %s:6379", REDIS_IP);

    int ntags = load_config((char*)CONFIG_PATH, &TAGS[0], MAX_TAGS);
    if (ntags == 0)
    {
        // Fallback для обратной совместимости, если конфига нет
        io::printn("Конфиг пуст/отсутствует — использую карту по умолчанию");
        TAGS[0].address = 0; // pressure
        TAGS[1].address = 1; // temp_01
        TAGS[2].address = 2; // pump_fb
        // имена по умолчанию (копируем побайтово, чтобы не зависеть от strcpy)
        char* d0 = "pressure"; char* d1 = "temp_01"; char* d2 = "pump_fb";
        for (usz i = 0; i < 9; i++) TAGS[0].name[i] = d0[i];
        for (usz i = 0; i < 8; i++) TAGS[1].name[i] = d1[i];
        for (usz i = 0; i < 8; i++) TAGS[2].name[i] = d2[i];
        ntags = 3;
    }

    // Сколько регистров читать: max(address)+1, но не больше MAX_REGS
    int max_addr = 0;
    for (int i = 0; i < ntags; i++)
    {
        if (TAGS[i].address > max_addr) max_addr = TAGS[i].address;
    }
    int nb = max_addr + 1;
    if (nb < 1) nb = 1;
    if (nb > MAX_REGS) nb = MAX_REGS;

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
    io::printn("Modbus подключен! Читаю %d регистров с 0", nb);

    void* redis_ctx = redisConnect((char*)REDIS_IP, 6379);
    if (redis_ctx == null || redisGetError(redis_ctx) != 0)
    {
        io::printn("Redis connect failed: %s", redisGetErrorStr(redis_ctx));
        modbus_close(modbus_ctx);
        modbus_free(modbus_ctx);
        return;
    }
    io::printn("Redis подключен!");

    ushort[125] regs;
    int cycle = 0;

    while (true)
    {
        int rc = modbus_read_registers(modbus_ctx, 0, nb, &regs[0]);
        if (rc != nb)
        {
            io::printn("Read failed cycle %d", cycle);
            time::sleep(500 * time::MS);
            // попробуй переподключиться
            modbus_close(modbus_ctx);
            modbus_connect(modbus_ctx);
            continue;
        }

        // Динамическая публикация: по одному HSET на тэг.
        // HSET latest_tags <name> <value> — эквивалентно одному большому HSET,
        // но работает с любым числом тэгов из конфига.
        // Масштабирование: публикуем сырое значение регистра как float.
        // Если датчику нужен делитель (например /10.0), добавь колонку scale
        // в Tag и в конфиг — сейчас простота важнее.
        for (int i = 0; i < ntags; i++)
        {
            int addr = TAGS[i].address;
            if (addr < 0 || addr >= nb) continue;
            float value = (float)regs[addr];
            redisCommand(redis_ctx, "HSET latest_tags %s %f", &TAGS[i].name[0], value);
        }

        // Также проверяем команды обратно от Logic Engine
        // HGET commands pump_01
        // Если есть команда, пишем в ПЛК
        // void* reply = redisCommand(redis_ctx, "HGET commands pump_01");
        // if (reply) -> modbus_write_register(ctx, 10, value)

        if (cycle % 20 == 0) // лог каждые 2 сек
        {
            io::printn("[%d] тэгов=%d regs=%d", cycle, ntags, nb);
        }

        cycle++;
        time::sleep(100 * time::MS); // 10 Гц опрос
    }

    modbus_close(modbus_ctx);
    modbus_free(modbus_ctx);
}
