// main.cpp
// Compile with something like:
//   g++ main.cpp kiss_fft.c -I. -lSDL2 -lGL -ldl -o m2sdr_app

#include "imgui.h"
#include "imgui_impl_sdl2.h"
#include "imgui_impl_opengl3.h"
#include <SDL.h>
#include <SDL_opengl.h>
#include <string>
#include "imnodes.h"

#include <cstdio>    // for printf
#include <cstdlib>   // for exit
#include <cstdint>   // for intxx_t
#include <cstring>   // for strncpy
#include <cmath>     // for sinf, cosf
#include <complex>
#include <vector>
#include <thread>
#include <chrono>
#include <deque>
#include <memory>
#include <mutex>

// KissFFT
#include "kiss_fft.h"
#include <math.h>    // for sqrtf

// TinyProcess
#include <process.hpp> // tiny-process-library header

// M2SDR
#include "liblitepcie.h"

// -----------------------------------------------------------------------------
// 1) I/Q Record Panel (unchanged from your snippet)
// -----------------------------------------------------------------------------

extern void m2sdr_record(const char *device_name,
                         const char *filename,
                         uint32_t size,
                         uint8_t zero_copy);
void m2sdr_record(const char *device_name,
                  const char *filename,
                  uint32_t size,
                  uint8_t zero_copy)
{
    printf("[m2sdr_record] device=%s, filename=%s, size=%u, zero_copy=%d\n",
           device_name, filename, size, zero_copy);
}

static char  sdr_device[128]      = "/dev/m2sdr0";
static char  record_filename[256] = "record_iq.bin";
static int   record_size          = 0;
static bool  use_zero_copy_record = false;

void ShowM2SDRIQRecordPanel()
{
    ImGui::SetNextWindowPos(ImVec2(10, 10), ImGuiCond_Always);
    ImGui::SetNextWindowSize(ImVec2(350, 220), ImGuiCond_Always);

    ImGui::Begin("M2SDR I/Q Record Utility", nullptr);
    {
        ImGui::InputText("Device", sdr_device, IM_ARRAYSIZE(sdr_device));
        ImGui::InputText("Filename", record_filename, IM_ARRAYSIZE(record_filename));
        ImGui::InputInt("Size (bytes)", &record_size);
        ImGui::Checkbox("Zero-Copy DMA", &use_zero_copy_record);

        ImGui::Separator();
        if (ImGui::Button("Start I/Q Record")) {
            uint8_t zero_copy_flag = use_zero_copy_record ? 1 : 0;
            m2sdr_record(sdr_device, record_filename, (uint32_t)record_size, zero_copy_flag);
        }
    }
    ImGui::End();
}

// -----------------------------------------------------------------------------
// m2sdr_tone */
// -----------------------------------------------------------------------------
static bool is_tone_process_running = false;
static std::unique_ptr<TinyProcessLib::Process> tone_process;
static int tone_freq = 1000;
static int tone_sample_rate = 30720000;
static float tone_amplitude = 1.0f;

void ShowM2SDRTonePanel()
{
    ImGui::SetNextWindowPos(ImVec2(10, 10), ImGuiCond_Always);
    ImGui::SetNextWindowSize(ImVec2(350, 220), ImGuiCond_Always);

    ImGui::Begin("M2SDR Tone Utility", nullptr);
    {
        ImGui::InputText("Device", sdr_device, IM_ARRAYSIZE(sdr_device));
        ImGui::InputInt("Frequency", &tone_freq);
        ImGui::InputInt("Sample Rate", &tone_sample_rate);
        ImGui::InputFloat("Amplitude", &tone_amplitude);
        ImGui::Checkbox("Zero-Copy DMA", &use_zero_copy_record);

        if (tone_amplitude > 1.0f)
            tone_amplitude = 1.0f;
        if (tone_amplitude < 0.0f)
            tone_amplitude = 0.0f;

        ImGui::Separator();
        if (ImGui::Button("Start M2SDR Tone") & !is_tone_process_running) {
            std::vector<std::string> args = {
                "../user/m2sdr_tone",
                "-f", std::to_string(tone_freq),
                "-s", std::to_string(tone_sample_rate),
                "-a", std::to_string(tone_amplitude)
            };
            if (use_zero_copy_record)
                args.push_back("-z");
            tone_process = std::unique_ptr<TinyProcessLib::Process>(new TinyProcessLib::Process(args, "", nullptr, nullptr, false));
            if (tone_process->get_id() > 0) {
                is_tone_process_running = true;
            }
        }

        ImGui::SameLine();

        if (ImGui::Button("Stop M2SDR Tone") & is_tone_process_running) {
            tone_process->kill();
            tone_process.reset();
            is_tone_process_running = false;
        }
    }
    ImGui::End();
}

// -----------------------------------------------------------------------------
// 2) I/Q Play Panel (unchanged)
// -----------------------------------------------------------------------------

extern void m2sdr_play(const char *device_name,
                       const char *filename,
                       uint32_t loops,
                       uint8_t zero_copy);
void m2sdr_play(const char *device_name,
                const char *filename,
                uint32_t loops,
                uint8_t zero_copy)
{
    printf("[m2sdr_play] device=%s, filename=%s, loops=%u, zero_copy=%d\n",
           device_name, filename, loops, zero_copy);
}

static char  play_device[128]   = "/dev/m2sdr0";
static char  play_filename[256] = "play_iq.bin";
static int   play_loops         = 1;
static bool  play_zero_copy     = false;

void ShowM2SDRIQPlayPanel()
{
    ImGui::SetNextWindowPos(ImVec2(370, 10), ImGuiCond_Always);
    ImGui::SetNextWindowSize(ImVec2(350, 220), ImGuiCond_Always);

    ImGui::Begin("M2SDR I/Q Play Utility", nullptr);
    {
        ImGui::InputText("Device", play_device, IM_ARRAYSIZE(play_device));
        ImGui::InputText("Filename", play_filename, IM_ARRAYSIZE(play_filename));
        ImGui::InputInt("Loops", &play_loops);
        ImGui::Checkbox("Zero-Copy DMA", &play_zero_copy);

        ImGui::Separator();
        if (ImGui::Button("Start I/Q Play")) {
            uint8_t zero_copy_flag = play_zero_copy ? 1 : 0;
            m2sdr_play(play_device, play_filename, (uint32_t)play_loops, zero_copy_flag);
        }
    }
    ImGui::End();
}

// -----------------------------------------------------------------------------
// 3) RF Utility Panel (unchanged)
// -----------------------------------------------------------------------------

extern "C" void m2sdr_init(
    uint32_t samplerate,
    int64_t  bandwidth,
    int64_t  refclk_freq,
    int64_t  tx_freq,
    int64_t  rx_freq,
    int64_t  tx_gain,
    int64_t  rx_gain,
    uint8_t  loopback,
    bool     bist_tx_tone,
    bool     bist_rx_tone,
    bool     bist_prbs,
    int32_t  bist_tone_freq,
    bool     enable_8bit_mode,
    bool     enable_oversample,
    const char *chan_mode,
    const char *sync_mode
);

void m2sdr_init(
    uint32_t samplerate,
    int64_t  bandwidth,
    int64_t  refclk_freq,
    int64_t  tx_freq,
    int64_t  rx_freq,
    int64_t  tx_gain,
    int64_t  rx_gain,
    uint8_t  loopback,
    bool     bist_tx_tone,
    bool     bist_rx_tone,
    bool     bist_prbs,
    int32_t  bist_tone_freq,
    bool     enable_8bit_mode,
    bool     enable_oversample,
    const char *chan_mode,
    const char *sync_mode
)
{
    printf("[m2sdr_init] samplerate=%u, bandwidth=%lld, tx_freq=%lld, rx_freq=%lld\n",
           samplerate, (long long)bandwidth, (long long)tx_freq, (long long)rx_freq);
}

static int64_t  g_refclk_freq    = 40000000LL; 
static uint32_t g_samplerate     = 2000000;
static int64_t  g_bandwidth      = 2000000;
static int64_t  g_tx_freq        = 2420000000LL;
static int64_t  g_rx_freq        = 2420000000LL;
static int64_t  g_tx_gain        = 0;
static int64_t  g_rx_gain        = 0;
static int      g_loopback       = 0;
static bool     g_bist_tx_tone   = false;
static bool     g_bist_rx_tone   = false;
static bool     g_bist_prbs      = false;
static int32_t  g_bist_tone_freq = 1000000;
static bool     g_enable_8bit    = false;
static bool     g_enable_oversample = false;

static int   g_chan_mode_idx = 1;  
static const char* chan_mode_options[] = { "1t1r", "2t2r" };

static int   g_sync_mode_idx = 0;  
static const char* sync_mode_options[] = { "internal", "external" };

static int   g_rf_device_num      = 0;
static char  g_rf_device_name[128]= "/dev/m2sdr0";

void ShowM2SDRRFPanel()
{
    ImGui::SetNextWindowPos(ImVec2(10, 240), ImGuiCond_Always);
    ImGui::SetNextWindowSize(ImVec2(710, 400), ImGuiCond_Always);

    ImGui::Begin("M2SDR RF Utility Panel", nullptr);
    {
        ImGui::InputInt("Device #", &g_rf_device_num);
        if (g_rf_device_num < 0) g_rf_device_num = 0;
        snprintf(g_rf_device_name, sizeof(g_rf_device_name),
                 "/dev/m2sdr%d", g_rf_device_num);
        ImGui::Text("Device Path: %s", g_rf_device_name);

        ImGui::Separator();

        ImGui::InputScalar("RefClk (Hz)",      ImGuiDataType_S64, &g_refclk_freq);
        ImGui::InputScalar("Samplerate (SPS)", ImGuiDataType_U32, &g_samplerate);
        ImGui::InputScalar("Bandwidth (Hz)",   ImGuiDataType_S64, &g_bandwidth);

        ImGui::InputScalar("TX freq (Hz)", ImGuiDataType_S64, &g_tx_freq);
        ImGui::InputScalar("RX freq (Hz)", ImGuiDataType_S64, &g_rx_freq);

        ImGui::InputScalar("TX gain (dB)", ImGuiDataType_S64, &g_tx_gain);
        ImGui::InputScalar("RX gain (dB)", ImGuiDataType_S64, &g_rx_gain);

        ImGui::InputInt("Loopback (0/1)", &g_loopback);

        ImGui::Checkbox("BIST TX Tone", &g_bist_tx_tone); ImGui::SameLine();
        ImGui::Checkbox("BIST RX Tone", &g_bist_rx_tone); ImGui::SameLine();
        ImGui::Checkbox("BIST PRBS",    &g_bist_prbs);
        ImGui::InputInt("BIST Tone Freq", &g_bist_tone_freq);

        ImGui::Checkbox("8-bit mode",      &g_enable_8bit); ImGui::SameLine();
        ImGui::Checkbox("Oversample",      &g_enable_oversample);

        ImGui::Text("Channel Mode:");
        ImGui::SameLine();
        ImGui::Combo("##chan_mode", &g_chan_mode_idx,
                     chan_mode_options, IM_ARRAYSIZE(chan_mode_options));

        ImGui::Text("Sync Mode:");
        ImGui::SameLine();
        ImGui::Combo("##sync_mode", &g_sync_mode_idx,
                     sync_mode_options, IM_ARRAYSIZE(sync_mode_options));

        ImGui::Separator();
        if (ImGui::Button("Initialize RF")) {
            const char* selected_chan_mode = chan_mode_options[g_chan_mode_idx];
            const char* selected_sync_mode = sync_mode_options[g_sync_mode_idx];
            m2sdr_init(
                g_samplerate,
                g_bandwidth,
                g_refclk_freq,
                g_tx_freq,
                g_rx_freq,
                g_tx_gain,
                g_rx_gain,
                (uint8_t)g_loopback,
                g_bist_tx_tone,
                g_bist_rx_tone,
                g_bist_prbs,
                g_bist_tone_freq,
                g_enable_8bit,
                g_enable_oversample,
                selected_chan_mode,
                selected_sync_mode
            );
        }
    }
    ImGui::End();
}

// -----------------------------------------------------------------------------
// 4) Large Buffers for FFT
// -----------------------------------------------------------------------------
static const int MAX_FFT_SAMPLES = 1 << 20;
//static float g_i_data[MAX_FFT_SAMPLES];
//static float g_q_data[MAX_FFT_SAMPLES];
//static float g_fft_data[MAX_FFT_SAMPLES];

// -----------------------------------------------------------------------------
// 5) Preconfigured FFT sizes
// -----------------------------------------------------------------------------
static const int s_fft_lengths[] = {
    128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768,
    65536, 131072, 262144, 524288, 1048576
};
static const int s_num_fft_lengths = (int)(sizeof(s_fft_lengths) / sizeof(s_fft_lengths[0]));
static int g_fft_length_index = 3; // default = 1024

static int GetFFTLength()
{
    return s_fft_lengths[g_fft_length_index];
}

// -----------------------------------------------------------------------------
// 6) Fake wave generation, KISS FFT, axis-plot
// -----------------------------------------------------------------------------
static float g_fake_freq_hz = 1e3;   
static float g_fake_amp     = 0.5f;
static float g_time_offset  = 0.0f;

static kiss_fft_cfg g_kiss_cfg = NULL;
static int g_kiss_n = 0;

static void ComputeFFT(const float *i_data, const float *q_data, float *fft_out, int n)
{
    if (g_kiss_cfg == NULL || g_kiss_n != n) {
        if (g_kiss_cfg) {
            free(g_kiss_cfg);
            g_kiss_cfg = NULL;
        }
        g_kiss_cfg = kiss_fft_alloc(n, 0, NULL, NULL);
        g_kiss_n = n;
    }

    static kiss_fft_cpx *cIn  = NULL;
    static kiss_fft_cpx *cOut = NULL;
    static int allocatedSize = 0;

    if (allocatedSize != n) {
        free(cIn);
        free(cOut);
        cIn  = (kiss_fft_cpx*)malloc(sizeof(kiss_fft_cpx) * n);
        cOut = (kiss_fft_cpx*)malloc(sizeof(kiss_fft_cpx) * n);
        allocatedSize = n;
    }

    for (int i = 0; i < n; i++) {
        cIn[i].r = i_data[i];
        cIn[i].i = q_data[i];
    }

    kiss_fft(g_kiss_cfg, cIn, cOut);

    for (int i = 0; i < n; i++) {
        float re = cOut[i].r;
        float im = cOut[i].i;
        fft_out[i] = sqrtf(re * re + im * im);
    }
}

static const float FIXED_PHASE_RAD = 3.1415926535f / 2.0f;

static void GenerateFakeIQ(float freq_hz, float amplitude, float time_offset, int n)
{
    (void)freq_hz;
    (void)amplitude;
    (void)time_offset;
    (void)n;
    //const float sample_rate = 1e6f;
    //if (n > MAX_FFT_SAMPLES) n = MAX_FFT_SAMPLES;

    //for (int i = 0; i < n; i++) {
    //    float t = (float)i / sample_rate;
    //    t += time_offset;
    //    //g_i_data[i] = amplitude * sinf(2.0f * 3.1415926535f * freq_hz * t);
    //    //g_q_data[i] = amplitude * sinf(2.0f * 3.1415926535f * freq_hz * t + FIXED_PHASE_RAD);
    //}
    //for (int i = n; i < MAX_FFT_SAMPLES; i++) {
    //    //g_i_data[i] = 0.0f;
    //    //g_q_data[i] = 0.0f;
    //}
}

// Minimal axis-drawing function for a 2D line plot in ImGui.
static void PlotLinesWithAxis(const char* label,
                              const float* data, int count,
                              float scale_min, float scale_max,
                              ImVec2 frame_size,
                              bool draw_unity_line)
{
    ImGui::BeginChild(label, frame_size, true /*border*/);

    ImVec2 p0 = ImGui::GetCursorScreenPos();
    ImVec2 p1 = ImVec2(p0.x + frame_size.x, p0.y + frame_size.y);

    ImDrawList* draw_list = ImGui::GetWindowDrawList();
    float range = (scale_max - scale_min);
    if (fabsf(range) < 1e-12f) range = 1.0f;

    auto YtoScreen = [&](float val) {
        float t = (val - scale_min) / range;
        return ImVec2(p0.x, p1.y - t * frame_size.y).y;
    };

    // y=0 axis
    if (scale_min <= 0.0f && scale_max >= 0.0f) {
        float zero_y = YtoScreen(0.0f);
        draw_list->AddLine(ImVec2(p0.x, zero_y), ImVec2(p1.x, zero_y),
                           IM_COL32(180,180,180,255));
    }
    // y=1 line if requested
    if (draw_unity_line && scale_min <= 1.0f && scale_max >= 1.0f) {
        float one_y = YtoScreen(1.0f);
        draw_list->AddLine(ImVec2(p0.x, one_y), ImVec2(p1.x, one_y),
                           IM_COL32(100,200,255,255));
    }
    // x=0 vertical axis
    draw_list->AddLine(ImVec2(p0.x, p0.y), ImVec2(p0.x, p1.y),
                       IM_COL32(180,180,180,255));

    ImGui::PushID(label);
    ImGui::SetCursorScreenPos(p0);
    ImGui::PlotLines("", data, count, 0, NULL,
                     scale_min, scale_max, frame_size);
    ImGui::PopID();

    ImGui::EndChild();
}

// -----------------------------------------------------------------------------
// 7) Waterfall Implementation
// -----------------------------------------------------------------------------
#define WATERFALL_WIDTH 1024
#define WATERFALL_HEIGHT 256

static float g_raw_waterfall[WATERFALL_HEIGHT][WATERFALL_WIDTH];
static int   g_raw_waterfall_nextrow = 0;
static bool  g_raw_enable_waterfall  = false;
static int   g_raw_waterfall_speed   = 1;   // frames between lines

static float g_fft_waterfall[WATERFALL_HEIGHT][WATERFALL_WIDTH];
static int   g_fft_waterfall_nextrow = 0;
static bool  g_fft_enable_waterfall  = false;
static int   g_fft_waterfall_speed   = 1;   // frames between lines

// Let's define 5 color maps
static const char* s_colormap_options[] = {
    "Grayscale",
    "Rainbow",
    "Viridis",
    "Plasma",
    "Magma"
};
static int g_fft_color_map_idx = 0; // default: Grayscale
static int g_raw_color_map_idx = 0; // default: Grayscale

static void AddWaterfallRow(int *g_waterfall_nextrow, float (&g_waterfall)[WATERFALL_HEIGHT][WATERFALL_WIDTH],
        const float* new_line, int length)
{
    int copy_len = (length > WATERFALL_WIDTH) ? WATERFALL_WIDTH : length;
    *g_waterfall_nextrow = (*g_waterfall_nextrow + 1) % WATERFALL_HEIGHT;

    for (int i = 0; i < copy_len; i++) {
        g_waterfall[*g_waterfall_nextrow][i] = new_line[i];
    }
    for (int i = copy_len; i < WATERFALL_WIDTH; i++) {
        g_waterfall[*g_waterfall_nextrow][i] = 0.0f;
    }
}

// We'll define multiple color maps:
static ImU32 MagnitudeToColor(float mag, float maxVal, int map_idx)
{
    // clamp
    float t = mag / maxVal;
    if (t < 0.0f) t = 0.0f;
    if (t > 1.0f) t = 1.0f;

    float r=0, g=0, b=0;

    switch (map_idx) {
    case 0: // Grayscale
        // 0 => black, 1 => white
        r = g = b = t;
        break;

    case 1: // Rainbow (simplistic black->blue->red->yellow->white approach)
        if (t < 0.25f) {
            float f = t / 0.25f; 
            r=0; g=0; b=f; 
        } else if (t < 0.5f) {
            float f = (t-0.25f)/0.25f;
            r=f; g=0; b=1.0f - f;
        } else if (t < 0.75f) {
            float f = (t-0.5f)/0.25f;
            r=1.0f; g=f; b=0;
        } else {
            float f = (t-0.75f)/0.25f;
            r=1.0f; g=1.0f; b=f;
        }
        break;

    case 2: // Viridis approx
        // We'll do a quick approximation: viridis is basically greenish->yellowish
        // This is not exact, but good enough for demonstration
        // t=0 => dark blue, t=1 => bright yellow
        if (t < 0.5f) {
            // move from dark blue(0.0,0.1,0.2) to green(0.0,0.7,0.3)
            float f = t*2;
            r = 0.0f + (0.0f-0.0f)*f;
            g = 0.1f + (0.7f-0.1f)*f;
            b = 0.2f + (0.3f-0.2f)*f;
        } else {
            float f = (t-0.5f)*2;
            // green(0.0,0.7,0.3) -> yellow(0.9,0.9,0.0)
            r = 0.0f + (0.9f-0.0f)*f;
            g = 0.7f + (0.9f-0.7f)*f;
            b = 0.3f + (0.0f-0.3f)*f;
        }
        break;

    case 3: // Plasma approx
        // a quick hack: dark purple->red->yellow
        if (t < 0.5f) {
            float f = t*2;
            // purple(0.2, 0.0, 0.3) -> red(1.0, 0.0, 0.0)
            r = 0.2f + (1.0f-0.2f)*f;
            g = 0.0f + (0.0f-0.0f)*f;
            b = 0.3f + (0.0f-0.3f)*f;
        } else {
            float f = (t-0.5f)*2;
            // red(1.0,0.0,0.0)-> yellow(1.0,1.0,0.0)
            r = 1.0f;
            g = 0.0f + (1.0f-0.0f)*f;
            b = 0.0f;
        }
        break;

    case 4: // Magma approx
        // dark(0.0,0.0,0.0)-> purple-> orange-> white
        if (t < 0.3f) {
            float f = t/0.3f;
            // black->dark purple
            r=0.0f + (0.3f)*f;
            g=0.0f;
            b=0.0f + (0.1f)*f;
        } else if (t < 0.6f) {
            float f = (t-0.3f)/0.3f;
            // purple->orange
            r=0.3f + (1.0f-0.3f)*f;
            g=0.0f + (0.4f)*f;
            b=0.1f + (0.0f-0.1f)*f;
        } else {
            float f = (t-0.6f)/0.4f;
            // orange->white
            r=1.0f;
            g=0.4f + (1.0f-0.4f)*f;
            b=0.0f + (1.0f-0.0f)*f;
        }
        break;
    }

    int R = (int)(255*r);
    int G = (int)(255*g);
    int B = (int)(255*b);
    return IM_COL32(R,G,B,255);
}

// We'll draw a child region (WATERFALL_WIDTH x WATERFALL_HEIGHT) 
static void ShowWaterfall(float (&g_waterfall)[WATERFALL_HEIGHT][WATERFALL_WIDTH],
        int g_waterfall_nextrow, int g_color_map_idx)
{
    ImGui::BeginChild("WaterfallView", ImVec2(WATERFALL_WIDTH, WATERFALL_HEIGHT), true);

    ImDrawList* draw_list = ImGui::GetWindowDrawList();
    ImVec2 p0 = ImGui::GetCursorScreenPos();

    for (int row = 0; row < WATERFALL_HEIGHT; row++) {
        int ring_row = (g_waterfall_nextrow - row + WATERFALL_HEIGHT) % WATERFALL_HEIGHT;
        for (int col = 0; col < WATERFALL_WIDTH; col++) {
            float mag = g_waterfall[ring_row][col];
            ImU32 col_u32 = MagnitudeToColor(mag, 500.0f, g_color_map_idx);

            float x = p0.x + (float)col;
            float y = p0.y + (float)(WATERFALL_HEIGHT - 1 - row);
            draw_list->AddRectFilled(ImVec2(x, y),
                                     ImVec2(x+1, y+1),
                                     col_u32);
        }
    }

    ImGui::EndChild();
}

// -----------------------------------------------------------------------------
// DMA Thread
// -----------------------------------------------------------------------------
static bool g_thread_fft_started = false;
static bool g_thread_fft_finish = false;
static bool g_thread_raw_iq_started = false;
static bool g_thread_raw_iq_finish = false;
static char raw_iq_device_name[256] = "/dev/m2sdr0";
static char fft_device_name[256] = "/dev/m2sdr1";
static bool fft_zero_copy = 0;
static int  g_plot_mode = 0;

// Data storage
// FFT
float g_fft_q_data[1024];
float g_fft_i_data[1024];
float g_fft_data[1024];
std::deque<float> fft_q_buffer;
std::deque<float> fft_i_buffer;
std::mutex fft_buffer_mutex;

// Raw I/Q
float g_raw_q_data[1024];
float g_raw_i_data[1024];
float g_raw_data[1024];
std::deque<float> raw_q_buffer;
std::deque<float> raw_i_buffer;
std::mutex raw_buffer_mutex;

void UpdateData(int id, const char *device_name,
        bool *thread_finish, bool *thread_started,
        int step, float scaling, std::mutex *buffer_mutex,
        std::deque<float> &i_buff, std::deque<float> &q_buff)
{
    struct litepcie_dma_ctrl dma = {.use_writer = 1};

    printf("Thread started %d\n", id);

    // loop until application end
    while (!*thread_finish) {
        printf("In the loop %d\n", id);

        // wait until stream start
        while (!*thread_started)
            std::this_thread::sleep_for(std::chrono::milliseconds(500));

        printf("start acquisition %d\n", id);
        if (*thread_finish) // Stop if requested
            break;

        printf("start acquisition2 %d\n", id);
        q_buff.clear();
        i_buff.clear();

        /* Initialize DMA. */
        printf("Thread%d: %s\n", id, device_name);
        if (litepcie_dma_init(&dma, device_name, fft_zero_copy))
            exit(1);

        dma.writer_enable = 1;
        printf("acquisition ready %d\n", id);

        // loop until
        while (*thread_started) {
            if (*thread_finish)
                break;
            /* Update DMA status. */
            litepcie_dma_process(&dma);

            /* Read from DMA. */
            while(1) {
                if (*thread_finish)
                    break;
                /* Get Read buffer. */
                char *buf_rd = litepcie_dma_next_read_buffer(&dma);
                /* Break when no buffer available for Read. */
                if (!buf_rd) {
                    break;
                }

                int16_t *samples = (int16_t *)buf_rd;
                size_t num_samples;
                num_samples = DMA_BUFFER_SIZE / (step * sizeof(int16_t));

                {
                    std::lock_guard<std::mutex> lock(*buffer_mutex);
                    for (size_t i = 0; i < num_samples; i++) {
                        i_buff.push_back((float)samples[step * i + 0] / scaling); // I, normalized
                        q_buff.push_back((float)samples[step * i + 1] / scaling); // Q, normalized
                    }
                }
            }
        }
        printf("acquisition stopped\n");

        /* Cleanup DMA. */
        litepcie_dma_cleanup(&dma);
        dma.writer_enable = 0;
    }
}

void fftThread()
{
    UpdateData(1, fft_device_name, &g_thread_fft_finish, &g_thread_fft_started,
        2, 1, &fft_buffer_mutex,
        std::ref(fft_i_buffer), std::ref(fft_q_buffer));
}

void rawIQThread()
{
    UpdateData(2, raw_iq_device_name, &g_thread_raw_iq_finish, &g_thread_raw_iq_started,
        4, 2047, &raw_buffer_mutex,
        std::ref(raw_i_buffer), std::ref(raw_q_buffer));
}
// -----------------------------------------------------------------------------
// 8) Master Plot Panel
// -----------------------------------------------------------------------------
static bool g_enable_fake_gen = false;
static bool g_animate_wave   = false;

static int  g_raw_waterfall_framecount = 0;
void ShowM2SDRRawIQPlotPanel()
{
    ImGui::SetNextWindowPos(ImVec2(10, 230), ImGuiCond_Always);
    ImGui::SetNextWindowSize(ImVec2(635, 800), ImGuiCond_Always);

    ImGui::Begin("M2SDR Plot Panel");

    ImGui::Text("Plot Mode:");
    ImGui::RadioButton("Raw I/Q", &g_plot_mode, 0);
    ImGui::SameLine();
    ImGui::RadioButton("FFT", &g_plot_mode, 1);

    ImGui::InputText("Device", raw_iq_device_name, IM_ARRAYSIZE(raw_iq_device_name));
    ImGui::Separator();

    ImGui::Checkbox("Enable Thread", &g_thread_raw_iq_started);

    ImGui::Separator();

    // Waterfall options
    if (g_plot_mode == 1) {
        ImGui::Checkbox("Waterfall", &g_raw_enable_waterfall);
        ImGui::SameLine();
        ImGui::InputInt("Wf Speed", &g_raw_waterfall_speed);
        if (g_raw_waterfall_speed < 1) g_raw_waterfall_speed = 1;

        // Color map selection
        ImGui::Text("Color Map:");
        if (ImGui::BeginCombo("##ColorMapCombo", s_colormap_options[g_raw_color_map_idx])) {
            for (int i = 0; i < IM_ARRAYSIZE(s_colormap_options); i++) {
                bool is_selected = (i == g_raw_color_map_idx);
                if (ImGui::Selectable(s_colormap_options[i], is_selected)) {
                    g_raw_color_map_idx = i;
                }
                if (is_selected) {
                    ImGui::SetItemDefaultFocus();
                }
            }
            ImGui::EndCombo();
        }
    } else {
        g_raw_enable_waterfall = false;
    }

    ImGui::Separator();

    int n = 1024;
    if (g_thread_raw_iq_started) {
        {
            std::lock_guard<std::mutex> lock(raw_buffer_mutex);
            if (!raw_q_buffer.empty() && !raw_i_buffer.empty() &&
                    (raw_q_buffer.size() >= 1024) && (raw_i_buffer.size() >= 1024)) {
                for (int i = 0;  i < n; i++) {
                    g_raw_i_data[i] = raw_i_buffer[i];
                    g_raw_q_data[i] = raw_q_buffer[i];
                }
                // Remove all unused samples
                raw_i_buffer.clear();
                raw_q_buffer.clear();
            }
        }
    }

    if (g_plot_mode == 1) {
        ComputeFFT(g_raw_i_data, g_raw_q_data, g_raw_data, n);
        if (g_raw_enable_waterfall) {
            g_raw_waterfall_framecount++;
            if (g_raw_waterfall_framecount % g_raw_waterfall_speed == 0) {
                AddWaterfallRow(&g_raw_waterfall_nextrow, g_raw_waterfall, g_raw_data, n);
            }
        }
    }

    ImGui::Text("Signal Plot (%d pts):", n);

    if (g_plot_mode == 0) {
        // Raw I/Q
        ImGui::Text("I samples:");
        PlotLinesWithAxis("IplotAxis", g_raw_i_data, n, -1.0f, 1.0f, ImVec2(512, 100), true);
        ImGui::Text("Q samples:");
        PlotLinesWithAxis("QplotAxis", g_raw_q_data, n, -1.0f, 1.0f, ImVec2(768, 200), true);
    } else {
        // FFT
        ImGui::Text("FFT Magnitude:");
        PlotLinesWithAxis("FFTAxis", g_raw_data, n, -2.0f, 500.0, ImVec2(768, 300), true);

        if (g_raw_enable_waterfall) {
            ImGui::Text("Waterfall (latest at bottom):");
            ShowWaterfall(g_raw_waterfall, g_raw_waterfall_nextrow, g_raw_color_map_idx);
        }
    }

    ImGui::End();
}

// -----------------------------------------------------------------------------
// FFT Plot Panel
// -----------------------------------------------------------------------------
static int  g_fft_waterfall_framecount = 0;

void ShowM2SDRFFTPlotPanel()
{
    ImGui::SetNextWindowPos(ImVec2(645, 10), ImGuiCond_Always);
    ImGui::SetNextWindowSize(ImVec2(1024, 800), ImGuiCond_Always);

    ImGui::Begin("M2SDR FFT Plot Panel");

    ImGui::InputText("Device", fft_device_name, IM_ARRAYSIZE(fft_device_name));
    ImGui::Separator();

    ImGui::Checkbox("Enable Thread", &g_thread_fft_started);

    ImGui::Separator();

    // Waterfall options
    ImGui::Checkbox("Waterfall", &g_fft_enable_waterfall);
    ImGui::SameLine();
    ImGui::InputInt("Wf Speed", &g_fft_waterfall_speed);
    if (g_fft_waterfall_speed < 1) g_fft_waterfall_speed = 1;

    // Color map selection
    ImGui::Text("Color Map:");
    if (ImGui::BeginCombo("##ColorMapCombo", s_colormap_options[g_fft_color_map_idx])) {
        for (int i = 0; i < IM_ARRAYSIZE(s_colormap_options); i++) {
            bool is_selected = (i == g_fft_color_map_idx);
            if (ImGui::Selectable(s_colormap_options[i], is_selected)) {
                g_fft_color_map_idx = i;
            }
            if (is_selected) {
                ImGui::SetItemDefaultFocus();
            }
        }
        ImGui::EndCombo();
    }

    ImGui::Separator();

    int n = 1024;

    if (g_fft_enable_waterfall) {
        g_fft_waterfall_framecount++;
        if (g_fft_waterfall_framecount % g_fft_waterfall_speed == 0) {
            AddWaterfallRow(&g_fft_waterfall_nextrow, g_fft_waterfall, g_fft_data, n);
        }
    }

    ImGui::Text("Signal Plot (%d pts):", n);

    // FFT
    float max_fft = 0;
    if (g_thread_fft_started) {
        {
            std::lock_guard<std::mutex> lock(fft_buffer_mutex);
            if (!fft_q_buffer.empty() && !fft_i_buffer.empty() &&
                    (fft_q_buffer.size() >= 1024) && (fft_i_buffer.size() >= 1024)) {
                for (int i = 0;  i < n; i++) {
                    std::complex<float> value(fft_i_buffer[i], fft_q_buffer[i]);
                    g_fft_data[i] = std::abs(value);
                    if (g_fft_data[i] > max_fft)
                        max_fft = g_fft_data[i];
                }
                // Remove all unused samples
                uint32_t length = (fft_i_buffer.size() / n) * n;
                fft_i_buffer.erase(fft_i_buffer.begin(), fft_i_buffer.begin() + length);
                fft_q_buffer.erase(fft_q_buffer.begin(), fft_q_buffer.begin() + length);
            }
        }
    }
    ImGui::Text("FFT Magnitude:");
    PlotLinesWithAxis("IplotAxis", g_fft_data, n, -2.0f, max_fft + 10, ImVec2(768, 300), true);
    if (g_fft_enable_waterfall) {
        ImGui::Text("Waterfall (latest at bottom):");
        ShowWaterfall(g_fft_waterfall, g_fft_waterfall_nextrow, g_fft_color_map_idx);
    }

    ImGui::End();
}

// Fake counters for each module
static int g_dma_tx_count     = 0;
static int g_datapath_tx_count= 0;
static int g_rfic_tx_count    = 0;
static int g_dma_rx_count     = 0;
static int g_datapath_rx_count= 0;
static int g_rfic_rx_count    = 0;

// A small utility to fake or randomize counters
static int FakeCounterValue(int &counter)
{
    // For demonstration, we'll just keep incrementing or do random
    // e.g. increment by a random small amount each frame
    counter += (rand() % 50); // random increment up to 49
    return counter;
}

void ShowM2SDRNodeDiagramPanel()
{
    // We can control the position/size if we want:
    ImGui::SetNextWindowPos(ImVec2(10, 500), ImGuiCond_Once);
    ImGui::SetNextWindowSize(ImVec2(600, 400), ImGuiCond_Once);

    ImGui::Begin("M2SDR Node Diagram");

    // Begin the node editor region
    ImNodes::BeginNodeEditor();

    // ------------------------------------------------------------------
    // Node 1: DMA TX
    // ------------------------------------------------------------------
    ImNodes::BeginNode(1);
    ImNodes::BeginNodeTitleBar();
    ImGui::TextUnformatted("DMA TX");
    ImNodes::EndNodeTitleBar();

    ImGui::Text("Samples: %d", FakeCounterValue(g_dma_tx_count));

    ImNodes::BeginOutputAttribute(11); 
    ImGui::Text("Out");
    ImNodes::EndOutputAttribute();

    ImNodes::EndNode();

    // ------------------------------------------------------------------
    // Node 2: Datapath TX
    // ------------------------------------------------------------------
    ImNodes::BeginNode(2);
    ImNodes::BeginNodeTitleBar();
    ImGui::TextUnformatted("Datapath TX");
    ImNodes::EndNodeTitleBar();

    ImNodes::BeginInputAttribute(21);
    ImGui::Text("In");
    ImNodes::EndInputAttribute();

    ImGui::Text("Samples: %d", FakeCounterValue(g_datapath_tx_count));

    ImNodes::BeginOutputAttribute(22); 
    ImGui::Text("Out");
    ImNodes::EndOutputAttribute();

    ImNodes::EndNode();

    // ------------------------------------------------------------------
    // Node 3: RFIC TX
    // ------------------------------------------------------------------
    ImNodes::BeginNode(3);
    ImNodes::BeginNodeTitleBar();
    ImGui::TextUnformatted("RFIC TX");
    ImNodes::EndNodeTitleBar();

    ImNodes::BeginInputAttribute(31);
    ImGui::Text("In");
    ImNodes::EndInputAttribute();

    ImGui::Text("Samples: %d", FakeCounterValue(g_rfic_tx_count));

    ImNodes::EndNode();

    // ------------------------------------------------------------------
    // Node 4: DMA RX
    // ------------------------------------------------------------------
    ImNodes::BeginNode(4);
    ImNodes::BeginNodeTitleBar();
    ImGui::TextUnformatted("DMA RX");
    ImNodes::EndNodeTitleBar();

    ImGui::Text("Samples: %d", FakeCounterValue(g_dma_rx_count));

    ImNodes::BeginOutputAttribute(44); 
    ImGui::Text("Out");
    ImNodes::EndOutputAttribute();

    ImNodes::EndNode();

    // ------------------------------------------------------------------
    // Node 5: Datapath RX
    // ------------------------------------------------------------------
    ImNodes::BeginNode(5);
    ImNodes::BeginNodeTitleBar();
    ImGui::TextUnformatted("Datapath RX");
    ImNodes::EndNodeTitleBar();

    ImNodes::BeginInputAttribute(51);
    ImGui::Text("In");
    ImNodes::EndInputAttribute();

    ImGui::Text("Samples: %d", FakeCounterValue(g_datapath_rx_count));

    ImNodes::BeginOutputAttribute(52); 
    ImGui::Text("Out");
    ImNodes::EndOutputAttribute();

    ImNodes::EndNode();

    // ------------------------------------------------------------------
    // Node 6: RFIC RX
    // ------------------------------------------------------------------
    ImNodes::BeginNode(6);
    ImNodes::BeginNodeTitleBar();
    ImGui::TextUnformatted("RFIC RX");
    ImNodes::EndNodeTitleBar();

    ImNodes::BeginInputAttribute(61);
    ImGui::Text("In");
    ImNodes::EndInputAttribute();

    ImGui::Text("Samples: %d", FakeCounterValue(g_rfic_rx_count));

    ImNodes::EndNode();

    // ------------------------------------------------------------------
    // Create links between nodes
    // ------------------------------------------------------------------
    ImNodes::Link(100, 11, 21); // DMA TX out -> Datapath TX in
    ImNodes::Link(101, 22, 31); // Datapath TX out -> RFIC TX in

    ImNodes::Link(102, 44, 51); // DMA RX out -> Datapath RX in
    ImNodes::Link(103, 52, 61); // Datapath RX out -> RFIC RX in

    // ------------------------------------------------------------------
    // Now that the nodes exist, we can set their positions in grid space
    // TX row across the top:
    ImNodes::SetNodeGridSpacePos(1, ImVec2( 50,  50)); // DMA TX
    ImNodes::SetNodeGridSpacePos(2, ImVec2(300, 50));  // Datapath TX
    ImNodes::SetNodeGridSpacePos(3, ImVec2(550, 50));  // RFIC TX

    // RX row across the bottom:
    ImNodes::SetNodeGridSpacePos(4, ImVec2( 50, 220)); // DMA RX
    ImNodes::SetNodeGridSpacePos(5, ImVec2(300, 220)); // Datapath RX
    ImNodes::SetNodeGridSpacePos(6, ImVec2(550, 220)); // RFIC RX

    // done
    ImNodes::EndNodeEditor();
    ImGui::End();
}


// -----------------------------------------------------------------------------
// Main
// -----------------------------------------------------------------------------

int main(int, char**)
{
    // SDL + OpenGL init
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_TIMER | SDL_INIT_GAMECONTROLLER) != 0) {
        printf("Error: %s\n", SDL_GetError());
        return -1;
    }
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_FLAGS, 0);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 2);

    SDL_WindowFlags window_flags =
        (SDL_WindowFlags)(SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE | SDL_WINDOW_ALLOW_HIGHDPI);
    SDL_Window* window = SDL_CreateWindow(
        "M2SDR Panels",
        SDL_WINDOWPOS_CENTERED,
        SDL_WINDOWPOS_CENTERED,
        1280,
        720,
        window_flags
    );
    SDL_GLContext gl_context = SDL_GL_CreateContext(window);
    SDL_GL_MakeCurrent(window, gl_context);
    SDL_GL_SetSwapInterval(1);

    // ImGui init
    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    ImGuiIO& io = ImGui::GetIO(); (void)io;
    ImGui::StyleColorsDark();

    ImNodes::CreateContext();

    ImGui_ImplSDL2_InitForOpenGL(window, gl_context);
    ImGui_ImplOpenGL3_Init("#version 130");

    // Start background data reading thread
    std::thread fft_data_thread(fftThread);
    std::thread raw_data_thread(rawIQThread);

    bool done = false;

    while (!done) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) {
                done = true;
            }

            ImGui_ImplSDL2_ProcessEvent(&event);
        }

        // Start ImGui frame
        ImGui_ImplOpenGL3_NewFrame();
        ImGui_ImplSDL2_NewFrame();
        ImGui::NewFrame();

        // The M2SDR Tone panel
        ShowM2SDRTonePanel();

        // The I/Q Record panel
        //ShowM2SDRIQRecordPanel();

        // The I/Q Play panel
        //ShowM2SDRIQPlayPanel();

        // The RF Utility panel
        //ShowM2SDRRFPanel();

        // The FFT Plot panel (FFT, Waterfall, etc.)
        ShowM2SDRFFTPlotPanel();

        // The FFT Plot panel (FFT, Waterfall, etc.)
        ShowM2SDRRawIQPlotPanel();

        // Our new Node Diagram
        //ShowM2SDRNodeDiagramPanel();

        // Rendering
        ImGui::Render();
        glViewport(0, 0, (int)io.DisplaySize.x, (int)io.DisplaySize.y);
        glClearColor(0.45f, 0.55f, 0.60f, 1.00f);
        glClear(GL_COLOR_BUFFER_BIT);
        ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());
        SDL_GL_SwapWindow(window);
    }

    // Stop m2sdr_tone process
    if (is_tone_process_running) {
        tone_process->kill();
        tone_process.reset();
        is_tone_process_running = false;
    }

    // Cleanup
    ImNodes::DestroyContext();
    ImGui_ImplOpenGL3_Shutdown();
    ImGui_ImplSDL2_Shutdown();
    ImGui::DestroyContext();

    SDL_GL_DeleteContext(gl_context);
    SDL_DestroyWindow(window);
    SDL_Quit();

    // Cleanup
    g_thread_fft_finish = true;
    g_thread_fft_started = true;
    fft_data_thread.join();
    g_thread_raw_iq_finish = true;
    g_thread_raw_iq_started = true;
    raw_data_thread.join();

    return 0;
}
