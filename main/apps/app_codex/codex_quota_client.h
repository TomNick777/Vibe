/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <cstdint>
#include <atomic>
#include <array>
#include <mutex>
#include <string>

namespace codex {

struct QuotaSnapshot {
    bool valid                 = false;
    bool cached                = false;
    bool wifiConnected         = false;
    bool processing            = false;
    int weeklyLeftPct          = -1;
    int fiveHourLeftPct        = -1;
    std::string fiveHourReset  = "--";
    bool fiveHourStale         = true;
    int grokbotWeeklyLeftPct   = -1;
    std::string grokbotWeeklyReset = "--";
    bool grokbotStale          = true;
    bool needsConfirmation    = false;
    std::string weeklyUsage    = "--";
    int weeklyDayStartLeftPct  = -1;
    int weeklySegmentStartLeftPct = -1;
    int weeklyTodayUsedPctPoints = 0;
    int weeklyResetCount       = 0;
    std::string weeklyTrackingPeriodStart = "";
    std::string status         = "idle";
    std::string petState       = "idle";
    std::string message        = "Quota waiting";
    std::string source         = "";
    std::string updatedAt      = "";
    bool stale                 = false;
    std::string hostName       = "";
    std::string sessionTitle   = "Codex Ready";
    std::string contextLabel   = "-- / --";
    int contextPressurePct     = 0;
    int compactThresholdPct    = -1;
    bool compactWarning        = false;
    std::string totalTokensLabel = "--";
    std::string modelLabel     = "--";
    std::string reasoningLabel = "--";
    std::string activityLabel  = "--";
    bool activityLive          = false;
    std::array<float, 24> activityBuckets = {};
    uint32_t sequence          = 0;
};

class QuotaClient {
public:
    void start();
    void stop();
    QuotaSnapshot snapshot();
    bool ingestPanelJson(const std::string& body, bool wifiConnected, const char* source);

private:
    void publish(QuotaSnapshot snapshot);
    bool parsePanelJson(const std::string& body, QuotaSnapshot& snapshot);
    QuotaSnapshot loadCachedSnapshot();
    void saveCachedSnapshot(const QuotaSnapshot& snapshot);

    std::mutex _mutex;
    QuotaSnapshot _snapshot;
    std::atomic_bool _running{false};
    uint32_t _last_cache_ms = 0;
    uint32_t _sequence        = 0;
};

}  // namespace codex
