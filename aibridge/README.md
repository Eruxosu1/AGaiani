# AniBridge: плагин для Studio (этап D)

Статус: **заготовка**, не собиралась и не проверялась. Цель описана в `docs/04_ARCHITECTURE.md`.

## Что нужно
1. **.NET SDK** (не Runtime): `dotnet --version` должен показывать версию. Visual Studio Code (с расширением C#) достаточно.
2. Игра в `E:\uTorria\Downloads\MOHS2` (путь в `AniBridge.csproj`, параметр `GamePath`).
3. Для исследования API: RuntimeUnityEditor (C#-консоль в игре), dnSpy, документация HS2API (все есть в MOHS2, см. `tools/mohs2` и `MOHS2_scan\summary.md`).

## Первое исследование (до кода)
В Studio открыть RuntimeUnityEditor, найти объект персонажа (`ChaControl`) и выяснить: как задаются выражение лица (шаблоны глаз, бровей, рта), открытие рта, взгляд; есть ли морфы (blendshapes) на лице. Результат записать в `docs/02_STATE.md`.

## Сборка (когда SDK установлен)
```
cd aibridge
dotnet build -c Release
```
Результат `bin\Release\net46\AniBridge.dll` положить в `MOHS2\Mods\[plugs]AniBridge\BepInEx\plugins\` и включить мод в Mod Organizer. Версия .NET (net46) и набор ссылок уточняются по файлам в `MOHS2\Data\StudioNEOV2_Data\Managed\`.
