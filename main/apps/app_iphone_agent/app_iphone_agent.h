// SPDX-License-Identifier: MIT
#pragma once
#include <apps/common/key_manager/key_manager.h>
#include <mooncake.h>
#include <lvgl.h>
#include <atomic>
#include <memory>

class AppIphoneAgent : public mooncake::AppAbility {
public:
    AppIphoneAgent();
    void onOpen() override;
    void onRunning() override;
    void onClose() override;
private:
    std::unique_ptr<input::KeyManager> _keys;
    lv_obj_t* _panel = nullptr;
    lv_obj_t* _state = nullptr;
    lv_obj_t* _links = nullptr;
    lv_obj_t* _count = nullptr;
    lv_obj_t* _action = nullptr;
    lv_obj_t* _action_label = nullptr;
    uint32_t _last_update = 0;
    std::atomic<bool> _toggle{false};
    void toggle();
    void update_view();
};
