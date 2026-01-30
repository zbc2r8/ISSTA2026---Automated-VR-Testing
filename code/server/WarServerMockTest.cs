// Mock test: send the server's test CSV from the VR app to the server (same format as live stream).
// Attach to a GameObject (e.g. in War scene), set Server Base Url and optionally Csv Path Override,
// then in Play mode use context menu: Run mock test (send server CSV to server).

using UnityEngine;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine.Networking;

public class WarServerMockTest : MonoBehaviour
{
    [Header("Mock test: send server test data to server")]
    public string ServerBaseUrl = "http://localhost:5000";

    [Tooltip("Leave empty to use StreamingAssets/WarTestData/gameover_war_data_5fps_p1_01.csv")]
    public string CsvPathOverride = "";

    public int MaxSequencesToSend = 20;
    public bool LogEachResponse = true;

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

    [ContextMenu("Run mock test (send server CSV to server)")]
    public void RunMockTest()
    {
        StartCoroutine(RunMockTestCoroutine());
    }

    private IEnumerator RunMockTestCoroutine()
    {
        string csvPath = GetCsvPath();
        if (!File.Exists(csvPath))
        {
            Debug.LogError("[WarServerMockTest] CSV not found: " + csvPath);
            yield break;
        }

        List<Dictionary<string, float>> rows = ParseCsvToFrames(csvPath);
        if (rows == null || rows.Count < 5)
        {
            Debug.LogError("[WarServerMockTest] Need at least 5 rows. Got: " + (rows != null ? rows.Count.ToString() : "0"));
            yield break;
        }

        Debug.Log("[WarServerMockTest] Loaded " + rows.Count + " frames. Sending sequences to " + ServerBaseUrl + " ...");

        int sent = 0, ok = 0;
        for (int i = 0; i <= rows.Count - 5 && sent < MaxSequencesToSend; i++, sent++)
        {
            var sequence = new List<Dictionary<string, float>>();
            for (int j = 0; j < 5; j++)
                sequence.Add(rows[i + j]);

            string json = BuildSequenceJson(sequence);
            using (UnityWebRequest req = new UnityWebRequest(ServerBaseUrl.TrimEnd('/') + "/predict", "POST"))
            {
                req.uploadHandler = new UploadHandlerRaw(System.Text.Encoding.UTF8.GetBytes(json));
                req.downloadHandler = new DownloadHandlerBuffer();
                req.SetRequestHeader("Content-Type", "application/json");
                yield return req.SendWebRequest();

                if (req.isDone && string.IsNullOrEmpty(req.error))
                {
                    ok++;
                    ParseAndLogResponse(req.downloadHandler.text, i, LogEachResponse);
                }
                else
                    Debug.LogWarning("[WarServerMockTest] Request " + (sent + 1) + " failed: " + req.error);
            }
        }

        Debug.Log("[WarServerMockTest] Done. Sent: " + sent + ", OK: " + ok);
    }

    private string GetCsvPath()
    {
        if (!string.IsNullOrEmpty(CsvPathOverride) && File.Exists(CsvPathOverride))
            return CsvPathOverride;
        string streaming = Path.Combine(Path.Combine(Application.streamingAssetsPath, "WarTestData"), "gameover_war_data_5fps_p1_01.csv");
        return streaming;
    }

    private List<Dictionary<string, float>> ParseCsvToFrames(string csvPath)
    {
        var frames = new List<Dictionary<string, float>>();
        var featureSet = new HashSet<string>(FRAME_FEATURE_COLS);
        string[] lines = File.ReadAllLines(csvPath);
        if (lines.Length < 2) return frames;

        string[] header = ParseCsvLine(lines[0]);
        for (int i = 1; i < lines.Length; i++)
        {
            string[] values = ParseCsvLine(lines[i]);
            var frame = new Dictionary<string, float>();
            for (int c = 0; c < header.Length && c < values.Length; c++)
            {
                if (!featureSet.Contains(header[c])) continue;
                float v;
                frame[header[c]] = float.TryParse(values[c], out v) ? v : 0f;
            }
            foreach (string col in FRAME_FEATURE_COLS)
                if (!frame.ContainsKey(col)) frame[col] = 0f;
            frames.Add(frame);
        }
        return frames;
    }

    private string[] ParseCsvLine(string line)
    {
        return line.Split(',');
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

    private void ParseAndLogResponse(string json, int sequenceIndex, bool log)
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
        if (log)
            Debug.Log("[WarServerMockTest] Seq " + sequenceIndex + " => prediction=" + pred + " confidence=" + conf.ToString("F3"));
    }
}
