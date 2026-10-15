// SPDX-License-Identifier: MIT
#include "view.h"
#include <hal/hal.h>

using namespace view;

void CodexView::init(lv_obj_t* parent)
{
    initVibe(parent);
}

void CodexView::update()
{
    updateVibe();
}

void CodexView::applySnapshot(const codex::QuotaSnapshot& snapshot)
{
    _vibe_full_redraw = _vibe_full_redraw ||
        snapshot.valid != _vibe_quota.valid || snapshot.stale != _vibe_quota.stale ||
        snapshot.cached != _vibe_quota.cached ||
        snapshot.weeklyLeftPct != _vibe_quota.weeklyLeftPct ||
        snapshot.fiveHourLeftPct != _vibe_quota.fiveHourLeftPct ||
        snapshot.fiveHourStale != _vibe_quota.fiveHourStale ||
        snapshot.grokbotWeeklyLeftPct != _vibe_quota.grokbotWeeklyLeftPct ||
        snapshot.grokbotStale != _vibe_quota.grokbotStale;
    _vibe_details_dirty = true;
    _vibe_quota = snapshot;
    _vibe_panel_at = GetHAL().millis();
    _state.processing = snapshot.processing;
}

void CodexView::applyBleState(bool connected)
{
    if (_state.bleConnected != connected) {
        _vibe_details_dirty = true;
        _vibe_full_redraw = true;
        _state.bleConnected = connected;
    }
}

void CodexView::setVoiceMode(VoiceMode mode)
{
    _voice_mode = mode;
}

uint32_t CodexView::frameIntervalMs() const
{
    return _state.bleConnected ? 50 : 100;
}
