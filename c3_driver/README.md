
# C3 Driver

Тут будет твой драйвер на C3.

1. Установи c3c: https://c3-lang.org
2. Установи libmodbus: sudo apt install libmodbus-dev
3. Компилируй: c3c compile modbus.c3 -l modbus -o driver
4. Вместо HTTP POST лучше сразу пиши в Redis через hiredis

Пример с hiredis:
```
import hiredis;
...
redisContext* c = redisConnect("127.0.0.1", 6379);
redisCommand(c, "HSET latest_tags pressure %f", regs[0]);
```
