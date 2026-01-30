using UnityEngine;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.IO;
using System;
using System.Text.RegularExpressions;
using System.Diagnostics; // Stopwatch only
using UnityEngine.Networking;

// ============================================================================
// PERFORMANCE MONITOR — minimal, C# 4.0 compatible
// ============================================================================
public static class PerformanceMonitor
{
    // OFF BY DEFAULT: baseline FPS run
    public static bool Enabled = false;

    private static Dictionary<string, List<float>> perfData = new Dictionary<string, List<float>>();

    public static void Record(string label, float value)
    {
        // FPS must always be logged (baseline needs it)
        if (label != "FPS" && !Enabled)
            return;

        List<float> list;
        if (!perfData.TryGetValue(label, out list))
        {
            list = new List<float>();
            perfData[label] = list;
        }
        list.Add(value);
    }

    public static void GenerateReport()
    {
        string txtPath = Application.persistentDataPath + "/perf_report.txt";
        string csvPath = Application.persistentDataPath + "/perf_report.csv";

        StreamWriter txt = new StreamWriter(txtPath, false);
        StreamWriter csv = new StreamWriter(csvPath, false);

        txt.WriteLine("=== PERFORMANCE REPORT === " + DateTime.Now);
        txt.WriteLine("InstrumentationEnabled: " + Enabled);
        txt.WriteLine("");

        csv.WriteLine("InstrumentationEnabled," + Enabled);
        csv.WriteLine("Label,Count,Avg,Min,Max,StdDev");

        foreach (KeyValuePair<string, List<float>> kv in perfData)
        {
            string label = kv.Key;
            List<float> values = kv.Value;
            if (values.Count == 0) continue;

            float sum = 0f;
            float min = float.MaxValue;
            float max = float.MinValue;

            foreach (float v in values)
            {
                sum += v;
                if (v < min) min = v;
                if (v > max) max = v;
            }

            float avg = sum / values.Count;

            float variance = 0f;
            foreach (float v in values)
            {
                float diff = v - avg;
                variance += diff * diff;
            }
            variance /= values.Count;
            float stddev = Mathf.Sqrt(variance);

            // TXT
            txt.WriteLine(label);
            txt.WriteLine(" Count:  " + values.Count);
            txt.WriteLine(" Avg:    " + avg.ToString("F2"));
            txt.WriteLine(" Min:    " + min.ToString("F2"));
            txt.WriteLine(" Max:    " + max.ToString("F2"));
            txt.WriteLine(" StdDev: " + stddev.ToString("F2"));
            txt.WriteLine("");

            // CSV
            csv.WriteLine(label + "," +
                values.Count + "," +
                avg.ToString("F2") + "," +
                min.ToString("F2") + "," +
                max.ToString("F2") + "," +
                stddev.ToString("F2"));
        }

        txt.Close();
        csv.Close();

        UnityEngine.Debug.Log("[PERF] Performance report saved:\n" + txtPath + "\n" + csvPath);
    }
}

// ============================================================================
// Shared prediction state for War scene / console display
// ============================================================================
public static class WarPredictionState
{
    public static int LastPrediction = -1;   // 0 or 1
    public static float LastConfidence = 0f;
    public static string Message = "";
    public static bool ServerEnabled = false;
}

// ============================================================================
// WAR LOGGER — stream to server + optional file log (file/screenshot commented out for overhead)
// ============================================================================
namespace Prefabs.Kinect
{
    public class DataLoggerScript_War : MonoBehaviour
    {
        private DataDictionary dataDictionary;
        private int itemCounter;
        private string outputPath;
        private string imagePath;
        private List<string> outputStream;

        public GameObject Player;
        private GameObject[] bombs;
        public GameObject Ground;
        public GameObject Passport;
        public GameObject Coin;
        public GameObject Suitcase;

        public Camera Cam;

        private float fpsTimer = 0f;

        [Header("Server prediction")]
        public string ServerBaseUrl = "http://localhost:5000";
        public bool UseServer = true;

        private List<Dictionary<string, float>> sequenceBuffer = new List<Dictionary<string, float>>();
        private List<float[]> bombPositionsThisFrame = new List<float[]>();
        private bool serverRequestInProgress = false;
        private float predictionLogCooldown = 0f;
        private const int SEQUENCE_LENGTH = 5;

        // Same 91 feature names as server meta.json frame_feature_cols
        private static readonly string[] FRAME_FEATURE_COLS = new string[]
        {
            "Bomb_0_X","Bomb_0_Y","Bomb_0_Z","Bomb_1_X","Bomb_1_Y","Bomb_1_Z",
            "Bomb_10_X","Bomb_10_Y","Bomb_10_Z","Bomb_11_X","Bomb_11_Y","Bomb_11_Z",
            "Bomb_2_X","Bomb_2_Y","Bomb_2_Z","Bomb_3_X","Bomb_3_Y","Bomb_3_Z",
            "Bomb_4_X","Bomb_4_Y","Bomb_4_Z","Bomb_5_X","Bomb_5_Y","Bomb_5_Z",
            "Bomb_6_X","Bomb_6_Y","Bomb_6_Z","Bomb_7_X","Bomb_7_Y","Bomb_7_Z",
            "Bomb_8_X","Bomb_8_Y","Bomb_8_Z","Bomb_9_X","Bomb_9_Y","Bomb_9_Z",
            "Coin_X","Coin_Y","Coin_Z","ElbowL_X","ElbowL_Y","ElbowL_Z",
            "ElbowR_X","ElbowR_Y","ElbowR_Z","FootL_X","FootL_Y","FootL_Z",
            "FootR_X","FootR_Y","FootR_Z","Ground_X","Ground_Y","Ground_Z",
            "HandL_X","HandL_Y","HandL_Z","HandR_X","HandR_Y","HandR_Z",
            "Head_X","Head_Y","Head_Z","KneeL_X","KneeL_Y","KneeL_Z",
            "KneeR_X","KneeR_Y","KneeR_Z","Passport_X","Passport_Y","Passport_Z",
            "Player_X","Player_Y","Player_Z","PlayerImage_X","PlayerImage_Y","PlayerImage_Z",
            "PlayerTransformEffect_X","PlayerTransformEffect_Y","PlayerTransformEffect_Z",
            "SpineBase_X","SpineBase_Y","SpineBase_Z","Suitcase_X","Suitcase_Y","Suitcase_Z",
            "Spatial_1","Temporal_1","Spatial_2","Temporal_2"
        };

        void Start()
        {
            dataDictionary = new DataDictionary();
            itemCounter = 0;
            outputStream = new List<string>();

            outputPath = Application.persistentDataPath + "/gameover_war/raw_data.json";
            imagePath = Application.persistentDataPath + "/gameover_war/image_log/";

            UnityEngine.Debug.Log("[WarLogger] WAR data (file logging commented out). Server: " + (UseServer ? ServerBaseUrl : "off"));

            WarPredictionState.ServerEnabled = UseServer;
            if (UseServer) PerformanceMonitor.Enabled = true;

            try { Cam = GameObject.FindWithTag("DataLoggerCamera").GetComponent<Camera>(); } catch { }

            InvokeRepeating("GatherData", 0.0f, 0.2f);
            // LogData commented out so file I/O does not affect overhead measurement
            // InvokeRepeating("LogData", 0.0f, 5.0f);
        }

        void Update()
        {
            fpsTimer += Time.deltaTime;
            if (fpsTimer >= 1f)
            {
                PerformanceMonitor.Record("FPS", 1f / Time.deltaTime);
                fpsTimer = 0f;
            }
            // Log prediction to console every 2s when server enabled
            if (WarPredictionState.ServerEnabled && WarPredictionState.LastPrediction >= 0)
            {
                predictionLogCooldown -= Time.deltaTime;
                if (predictionLogCooldown <= 0f)
                {
                    UnityEngine.Debug.Log("[WarLogger] " + WarPredictionState.Message);
                    predictionLogCooldown = 2f;
                }
            }
        }

        // ============================================================================
        // GatherData — build flat frame for server; file/screenshot commented out for overhead
        // ============================================================================
        private void GatherData()
        {
            dataDictionary.values.Clear();
            bombPositionsThisFrame.Clear();

            TrySave(Player);
            TrySave(Ground);
            TrySave(Passport);
            TrySave(Coin);
            TrySave(Suitcase);

            bombs = GameObject.FindGameObjectsWithTag("Bomb");
            if (bombs != null)
            {
                for (int i = 0; i < bombs.Length; i++)
                {
                    TrySave(bombs[i]);
                    try
                    {
                        Vector3 p = bombs[i].transform.position;
                        bombPositionsThisFrame.Add(new float[] { p.x, p.y, p.z });
                    }
                    catch { }
                }
            }

            string dt = DateTime.Now.ToString("MM/dd/yyyy hh:mm:ss.fff");
            dataDictionary.datetime = dt;

            // Optional: keep JSON in memory for file logging later (commented out to avoid overhead)
            // string json = SaveCustomJSON(dataDictionary);
            // outputStream.Add(json);

            // Build flat 91-feature frame and add to sequence buffer
            Dictionary<string, float> frame = BuildFlatFrame(dataDictionary, bombPositionsThisFrame);
            sequenceBuffer.Add(frame);
            while (sequenceBuffer.Count > SEQUENCE_LENGTH)
                sequenceBuffer.RemoveAt(0);

            if (UseServer && sequenceBuffer.Count == SEQUENCE_LENGTH && !serverRequestInProgress)
            {
                var copy = new List<Dictionary<string, float>>(sequenceBuffer);
                StartCoroutine(SendSequenceToServer(copy));
                serverRequestInProgress = true;
            }

            // Screenshot/file logging commented out so it does not interfere with overhead measurement
            // int w = Screen.height; int h = Screen.height;
            // RenderTexture rt = new RenderTexture(w, h, 16); Cam.targetTexture = rt; ...
            // File.WriteAllBytes(imagePath + dt_id + ".png", arr);
        }


        // ============================================================================
        // SAFE TrySave
        // ============================================================================
        private void TrySave(GameObject obj)
        {
            if (obj == null) return;

            Transform t = null;

            try { t = obj.transform; }
            catch { return; }

            if (t == null) return;

            // SaveTransform always needed for baseline data
            try { SaveTransform(t); }
            catch { }
        }


        // ============================================================================
        // SaveTransform — no timing when instrumentation disabled
        // ============================================================================
        private int SaveTransform(Transform t)
        {
            if (t == null) return -1;

            BaseLogTemplate data = new BaseLogTemplate();
            int id = itemCounter++;

            data.Name = t.name;
            data.ChildCount = t.childCount;

            data.EulerAngles = new float[] { t.eulerAngles.x, t.eulerAngles.y, t.eulerAngles.z };
            data.LocalEulerAngles = new float[] { t.localEulerAngles.x, t.localEulerAngles.y, t.localEulerAngles.z };
            data.LocalPosition = new float[] { t.localPosition.x, t.localPosition.y, t.localPosition.z };
            data.LocalRotation = new float[] { t.localRotation.x, t.localRotation.y, t.localRotation.z, t.localRotation.w };
            data.LocalScale = new float[] { t.localScale.x, t.localScale.y, t.localScale.z };
            data.Position = new float[] { t.position.x, t.position.y, t.position.z };
            data.Rotation = new float[] { t.rotation.x, t.rotation.y, t.rotation.z, t.rotation.w };

            data.ParentName = (t.parent != null) ? t.parent.name : "root";

            List<int> children = new List<int>();

            for (int i = 0; i < t.childCount; i++)
            {
                Transform c = t.GetChild(i);

                if (!IsLoggableObject(c.gameObject))
                    continue;

                try { children.Add(SaveTransform(c)); }
                catch { }
            }

            data.Children = children.ToArray();
            dataDictionary.values.Add(id, data);

            return id;
        }

        private bool IsLoggableObject(GameObject obj)
        {
            string n = obj.name;
            return n.Contains("Player")
                || n.Contains("Hand")
                || n.Contains("Foot")
                || n.Contains("Head")
                || n.Contains("Elbow")
                || n.Contains("Spine")
                || n.Contains("Knee")
                || n.Contains("Ground")
                || n.Contains("Passport")
                || n.Contains("Coin")
                || n.Contains("Suitcase")
                || n.Contains("Bomb");
        }

        // Map Unity object Name to server feature prefix (War: Head, SpineBase, ElbowL, etc.)
        private static string GetServerKeyPrefix(string name)
        {
            if (string.IsNullOrEmpty(name)) return null;
            if (name.Contains("Head")) return "Head";
            if (name.Contains("Spine")) return "SpineBase";
            if (name.Contains("ElbowL") || name == "ElbowL") return "ElbowL";
            if (name.Contains("ElbowR") || name == "ElbowR") return "ElbowR";
            if (name.Contains("HandL") || name == "HandL") return "HandL";
            if (name.Contains("HandR") || name == "HandR") return "HandR";
            if (name.Contains("KneeL") || name == "KneeL") return "KneeL";
            if (name.Contains("KneeR") || name == "KneeR") return "KneeR";
            if (name.Contains("FootL") || name == "FootL") return "FootL";
            if (name.Contains("FootR") || name == "FootR") return "FootR";
            if (name.Contains("Ground")) return "Ground";
            if (name.Contains("Coin")) return "Coin";
            if (name.Contains("Passport")) return "Passport";
            if (name.Contains("Suitcase")) return "Suitcase";
            if (name.Contains("PlayerImage")) return "PlayerImage";
            if (name.Contains("PlayerTransformEffect")) return "PlayerTransformEffect";
            if (name == "Player" || (name.Contains("Player") && !name.Contains("PlayerImage") && !name.Contains("PlayerTransformEffect"))) return "Player";
            return null;
        }

        private Dictionary<string, float> BuildFlatFrame(DataDictionary d, List<float[]> bombPositions)
        {
            var frame = new Dictionary<string, float>();
            foreach (string key in FRAME_FEATURE_COLS)
                frame[key] = 0f;

            foreach (var kv in d.values)
            {
                string prefix = GetServerKeyPrefix(kv.Value.Name);
                if (prefix == null) continue;
                float[] pos = kv.Value.Position;
                if (pos == null || pos.Length < 3) continue;
                frame[prefix + "_X"] = pos[0];
                frame[prefix + "_Y"] = pos[1];
                frame[prefix + "_Z"] = pos[2];
            }

            for (int i = 0; i < bombPositions.Count && i < 12; i++)
            {
                float[] p = bombPositions[i];
                if (p == null || p.Length < 3) continue;
                string b = "Bomb_" + i + "_";
                frame[b + "X"] = p[0];
                frame[b + "Y"] = p[1];
                frame[b + "Z"] = p[2];
            }

            frame["Spatial_1"] = 0f;
            frame["Temporal_1"] = 0f;
            frame["Spatial_2"] = 0f;
            frame["Temporal_2"] = 0f;
            return frame;
        }

        private string BuildSequenceJson(List<Dictionary<string, float>> sequence)
        {
            var frameStrings = new List<string>();
            foreach (var frame in sequence)
            {
                var parts = new List<string>();
                foreach (string key in FRAME_FEATURE_COLS)
                    parts.Add("\"" + key + "\":" + (frame.ContainsKey(key) ? frame[key].ToString("R") : "0"));
                frameStrings.Add("{" + string.Join(",", parts.ToArray()) + "}");
            }
            return "{\"sequence\":[" + string.Join(",", frameStrings.ToArray()) + "]}";
        }

        private IEnumerator SendSequenceToServer(List<Dictionary<string, float>> sequence)
        {
            string json = BuildSequenceJson(sequence);
            string url = ServerBaseUrl.TrimEnd('/') + "/predict";
            float startTime = Time.realtimeSinceStartup;

            using (UnityWebRequest req = new UnityWebRequest(url, "POST"))
            {
                req.uploadHandler = new UploadHandlerRaw(System.Text.Encoding.UTF8.GetBytes(json));
                req.downloadHandler = new DownloadHandlerBuffer();
                req.SetRequestHeader("Content-Type", "application/json");
                yield return req.SendWebRequest();

                float elapsedMs = (Time.realtimeSinceStartup - startTime) * 1000f;
                PerformanceMonitor.Record("ServerRequestMs", elapsedMs);

                if (req.isDone && string.IsNullOrEmpty(req.error))
                {
                    string responseText = req.downloadHandler.text;
                    ParsePredictResponse(responseText);
                }
                else
                {
                    UnityEngine.Debug.LogWarning("[WarLogger] Server request failed: " + req.error);
                    WarPredictionState.LastPrediction = -1;
                    WarPredictionState.Message = "Server error: " + req.error;
                }
            }
            serverRequestInProgress = false;
        }

        private void ParsePredictResponse(string json)
        {
            try
            {
                int pred = -1;
                if (json.IndexOf("\"prediction\":0") >= 0) pred = 0;
                else if (json.IndexOf("\"prediction\":1") >= 0) pred = 1;

                float conf = 0f;
                int probStart = json.IndexOf("\"probabilities\":[");
                if (probStart >= 0)
                {
                    int bracket = json.IndexOf(']', probStart);
                    if (bracket > probStart)
                    {
                        string arr = json.Substring(probStart + 16, bracket - probStart - 16);
                        string[] parts = arr.Split(',');
                        if (parts.Length >= 2 && pred >= 0)
                        {
                            float p0, p1;
                            if (float.TryParse(parts[0].Trim(), out p0) && float.TryParse(parts[1].Trim(), out p1))
                                conf = pred == 0 ? p0 : p1;
                        }
                    }
                }

                WarPredictionState.LastPrediction = pred;
                WarPredictionState.LastConfidence = conf;
                WarPredictionState.Message = "Prediction: " + pred + " | Confidence: " + conf.ToString("F2");
            }
            catch (Exception e)
            {
                WarPredictionState.LastPrediction = -1;
                WarPredictionState.Message = "Parse error: " + e.Message;
            }
        }

        // ============================================================================
        // JSON GENERATION (kept for optional file logging)
        // ============================================================================
        string SaveCustomJSON(DataDictionary d)
        {
            string output = "{";
            output += "\"datetime\": \"" + d.datetime + "\",";
            output += "\"values\":{";

            foreach (KeyValuePair<int, BaseLogTemplate> v in d.values)
            {
                output += "\"" + v.Key + "\":{";
                output += "\"Name\":\"" + v.Value.Name + "\",";
                output += "\"ChildCount\":" + v.Value.ChildCount + ",";
                output += "\"Children\":[" + string.Join(",", v.Value.Children.Select(x => x.ToString()).ToArray()) + "],";
                output += "\"EulerAngles\":[" + string.Join(",", v.Value.EulerAngles.Select(x => x.ToString()).ToArray()) + "],";
                output += "\"LocalEulerAngles\":[" + string.Join(",", v.Value.LocalEulerAngles.Select(x => x.ToString()).ToArray()) + "],";
                output += "\"LocalPosition\":[" + string.Join(",", v.Value.LocalPosition.Select(x => x.ToString()).ToArray()) + "],";
                output += "\"LocalRotation\":[" + string.Join(",", v.Value.LocalRotation.Select(x => x.ToString()).ToArray()) + "],";
                output += "\"LocalScale\":[" + string.Join(",", v.Value.LocalScale.Select(x => x.ToString()).ToArray()) + "],";
                output += "\"ParentName\":\"" + v.Value.ParentName + "\",";
                output += "\"Position\":[" + string.Join(",", v.Value.Position.Select(x => x.ToString()).ToArray()) + "],";
                output += "\"Rotation\":[" + string.Join(",", v.Value.Rotation.Select(x => x.ToString()).ToArray()) + "]";
                output += "},";
            }

            output = output.TrimEnd(',');
            output += "}}";

            return output;
        }

        // ============================================================================
        void OnApplicationQuit()
        {
            // ALWAYS generate report — with FPS even if Enabled = false
            PerformanceMonitor.GenerateReport();
        }

        // ============================================================================
        // DATA STRUCTURES
        // ============================================================================
        [System.Serializable]
        public class DataDictionary
        {
            public string datetime;
            public Dictionary<int, BaseLogTemplate> values = new Dictionary<int, BaseLogTemplate>();
        }

        [System.Serializable]
        public class BaseLogTemplate
        {
            public string Name { get; set; }
            public int ChildCount { get; set; }
            public int[] Children { get; set; }
            public float[] EulerAngles { get; set; }
            public float[] LocalEulerAngles { get; set; }
            public float[] LocalPosition { get; set; }
            public float[] LocalRotation { get; set; }
            public float[] LocalScale { get; set; }
            public string ParentName { get; set; }
            public float[] Position { get; set; }
            public float[] Rotation { get; set; }
        }
    }
}

