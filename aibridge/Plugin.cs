// ЗАГОТОВКА (этап D). Не собиралась и не проверялась.
// Задача плагина: принимать команды по локальному WebSocket (см. docs/04_ARCHITECTURE.md)
// и управлять персонажем в Studio: выражение лица, рот по громкости аудио, поза/анимация, камера,
// покадровая съёмка с фиксированным шагом. Сначала доказываем в RuntimeUnityEditor, какие вызовы нужны.
using BepInEx;

namespace AniBridge
{
    [BepInPlugin(Guid, "AniBridge", "0.0.1")]
    [BepInProcess("StudioNEOV2")]
    public class AniBridgePlugin : BaseUnityPlugin
    {
        public const string Guid = "agaiani.anibridge";

        private void Awake()
        {
            Logger.LogInfo("AniBridge loaded (stub, no commands yet)");
            // TODO: поднять WebSocket на 127.0.0.1:<порт>, разобрать JSON-команды из docs/04_ARCHITECTURE.md
        }
    }
}
