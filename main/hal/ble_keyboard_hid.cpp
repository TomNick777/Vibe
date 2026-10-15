// SPDX-License-Identifier: MIT
// Standard keyboard portion adapted from liptoxli/M5stopwatch-vibecoding.
// Vibe deliberately exposes no Codex Micro vendor or directional control reports.
#include "ble_keyboard_hid.h"
#include <cstdint>
#include <esp_log.h>
#include <host/ble_att.h>
#include <host/ble_gatt.h>
#include <host/ble_hs.h>
#include <host/ble_uuid.h>
#include <os/os_mbuf.h>

namespace {
constexpr const char* kTag = "Vibe-Keyboard";
constexpr uint8_t kKeyboardReportId = 1;
const ble_uuid16_t kHidServiceUuid = BLE_UUID16_INIT(0x1812);
const ble_uuid16_t kProtocolModeUuid = BLE_UUID16_INIT(0x2A4E);
const ble_uuid16_t kReportMapUuid = BLE_UUID16_INIT(0x2A4B);
const ble_uuid16_t kReportUuid = BLE_UUID16_INIT(0x2A4D);
const ble_uuid16_t kHidInfoUuid = BLE_UUID16_INIT(0x2A4A);
const ble_uuid16_t kControlPointUuid = BLE_UUID16_INIT(0x2A4C);
const ble_uuid16_t kReportReferenceUuid = BLE_UUID16_INIT(0x2908);
const ble_uuid16_t kBootKeyboardInputUuid = BLE_UUID16_INIT(0x2A22);
const ble_uuid16_t kBootKeyboardOutputUuid = BLE_UUID16_INIT(0x2A32);

const uint8_t kKeyboardReportMap[] = {
    0x05, 0x01,  // Usage Page (Generic Desktop)
    0x09, 0x06,  // Usage (Keyboard)
    0xA1, 0x01,  // Collection (Application)
    0x85, kKeyboardReportId,
    0x05, 0x07,
    0x19, 0xE0,
    0x29, 0xE7,
    0x15, 0x00,
    0x25, 0x01,
    0x75, 0x01,
    0x95, 0x08,
    0x81, 0x02,
    0x95, 0x01,
    0x75, 0x08,
    0x81, 0x01,
    0x95, 0x05,
    0x75, 0x01,
    0x05, 0x08,
    0x19, 0x01,
    0x29, 0x05,
    0x91, 0x02,
    0x95, 0x01,
    0x75, 0x03,
    0x91, 0x01,
    0x95, 0x06,
    0x75, 0x08,
    0x15, 0x00,
    0x26, 0xE7, 0x00,
    0x05, 0x07,
    0x19, 0x00,
    0x2A, 0xE7, 0x00,
    0x81, 0x00,
    0xC0,

};

const uint8_t kKeyboardInputReportReference[2] = {kKeyboardReportId, 0x01};
const uint8_t kKeyboardOutputReportReference[2] = {kKeyboardReportId, 0x02};
const uint8_t kHidInfo[4] = {0x11, 0x01, 0x00, 0x01};
enum class Attribute : uintptr_t {
    ProtocolMode = 1, ReportMap, KeyboardInputReport, KeyboardOutputReport,
    HidInfo, ControlPoint, BootKeyboardInput, BootKeyboardOutput,
};
uint16_t g_keyboard_input_handle = 0;
uint16_t g_keyboard_output_handle = 0;
uint16_t g_boot_keyboard_input_handle = 0;
uint16_t g_boot_keyboard_output_handle = 0;
uint8_t g_protocol_mode = 1;
uint8_t g_control_point = 0;
uint8_t g_keyboard_input_report[8] = {};
uint8_t g_keyboard_output_report = 0;
uint8_t g_boot_keyboard_input_report[8] = {};
uint8_t g_boot_keyboard_output_report = 0;

Attribute attribute_from_arg(void* arg) {
    return static_cast<Attribute>(reinterpret_cast<uintptr_t>(arg));
}
int append_value(os_mbuf* om, const void* data, size_t length) {
    return os_mbuf_append(om, data, length) == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
}
int gatt_access(uint16_t, uint16_t, ble_gatt_access_ctxt* ctxt, void* arg)
{
    if (!ctxt) {
        return BLE_ATT_ERR_UNLIKELY;
    }

    const Attribute attribute = attribute_from_arg(arg);
    switch (attribute) {
    case Attribute::ProtocolMode:
        if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
            return append_value(ctxt->om, &g_protocol_mode, sizeof(g_protocol_mode));
        }
        if (ctxt->op == BLE_GATT_ACCESS_OP_WRITE_CHR) {
            return ble_hs_mbuf_to_flat(ctxt->om, &g_protocol_mode, sizeof(g_protocol_mode), nullptr) == 0
                ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
        }
        break;
    case Attribute::ReportMap:
        if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
            return append_value(ctxt->om, kKeyboardReportMap, sizeof(kKeyboardReportMap));
        }
        break;
    case Attribute::KeyboardInputReport:
        if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
            return append_value(ctxt->om,
                                g_keyboard_input_report,
                                sizeof(g_keyboard_input_report));
        }
        break;
    case Attribute::KeyboardOutputReport:
        if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
            return append_value(ctxt->om,
                                &g_keyboard_output_report,
                                sizeof(g_keyboard_output_report));
        }
        if (ctxt->op == BLE_GATT_ACCESS_OP_WRITE_CHR) {
            return ble_hs_mbuf_to_flat(ctxt->om,
                                       &g_keyboard_output_report,
                                       sizeof(g_keyboard_output_report),
                                       nullptr) == 0
                ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
        }
        break;
    case Attribute::HidInfo:
        if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
            return append_value(ctxt->om, kHidInfo, sizeof(kHidInfo));
        }
        break;
    case Attribute::ControlPoint:
        if (ctxt->op == BLE_GATT_ACCESS_OP_WRITE_CHR) {
            return ble_hs_mbuf_to_flat(ctxt->om, &g_control_point, sizeof(g_control_point), nullptr) == 0
                ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
        }
        break;
    case Attribute::BootKeyboardInput:
        if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
            return append_value(ctxt->om,
                                g_boot_keyboard_input_report,
                                sizeof(g_boot_keyboard_input_report));
        }
        break;
    case Attribute::BootKeyboardOutput:
        if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
            return append_value(ctxt->om,
                                &g_boot_keyboard_output_report,
                                sizeof(g_boot_keyboard_output_report));
        }
        if (ctxt->op == BLE_GATT_ACCESS_OP_WRITE_CHR) {
            return ble_hs_mbuf_to_flat(ctxt->om,
                                       &g_boot_keyboard_output_report,
                                       sizeof(g_boot_keyboard_output_report),
                                       nullptr) == 0
                ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
        }
        break;
    }
    return BLE_ATT_ERR_UNLIKELY;
}
int report_reference_access(uint16_t, uint16_t, ble_gatt_access_ctxt* ctxt, void* arg) {
    if (!ctxt || ctxt->op != BLE_GATT_ACCESS_OP_READ_DSC) return BLE_ATT_ERR_UNLIKELY;
    const uint8_t* reference = arg == &g_keyboard_input_handle ? kKeyboardInputReportReference
                            : arg == &g_keyboard_output_handle ? kKeyboardOutputReportReference : nullptr;
    return reference ? append_value(ctxt->om, reference, 2) : BLE_ATT_ERR_UNLIKELY;
}
#define REPORT_DESCRIPTOR_ARRAY(name, handle) \
ble_gatt_dsc_def name[] = { \
    { \
        .uuid = &kReportReferenceUuid.u, \
        .att_flags = BLE_ATT_F_READ, \
        .min_key_size = 0, \
        .access_cb = report_reference_access, \
        .arg = &(handle), \
    }, \
    {}, \
}

REPORT_DESCRIPTOR_ARRAY(kKeyboardInputDescriptors, g_keyboard_input_handle);
REPORT_DESCRIPTOR_ARRAY(kKeyboardOutputDescriptors, g_keyboard_output_handle);

#undef REPORT_DESCRIPTOR_ARRAY

const ble_gatt_chr_def kCharacteristics[] = {
    {
        .uuid = &kProtocolModeUuid.u,
        .access_cb = gatt_access,
        .arg = reinterpret_cast<void*>(static_cast<uintptr_t>(Attribute::ProtocolMode)),
        .descriptors = nullptr,
        .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_WRITE_NO_RSP,
        .min_key_size = 0,
        .val_handle = nullptr,
        .cpfd = nullptr,
    },
    {
        .uuid = &kReportMapUuid.u,
        .access_cb = gatt_access,
        .arg = reinterpret_cast<void*>(static_cast<uintptr_t>(Attribute::ReportMap)),
        .descriptors = nullptr,
        .flags = BLE_GATT_CHR_F_READ,
        .min_key_size = 0,
        .val_handle = nullptr,
        .cpfd = nullptr,
    },
    {
        .uuid = &kReportUuid.u,
        .access_cb = gatt_access,
        .arg = reinterpret_cast<void*>(static_cast<uintptr_t>(Attribute::KeyboardInputReport)),
        .descriptors = kKeyboardInputDescriptors,
        .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_NOTIFY,
        .min_key_size = 0,
        .val_handle = &g_keyboard_input_handle,
        .cpfd = nullptr,
    },
    {
        .uuid = &kReportUuid.u,
        .access_cb = gatt_access,
        .arg = reinterpret_cast<void*>(static_cast<uintptr_t>(Attribute::KeyboardOutputReport)),
        .descriptors = kKeyboardOutputDescriptors,
        .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_WRITE | BLE_GATT_CHR_F_WRITE_NO_RSP,
        .min_key_size = 0,
        .val_handle = &g_keyboard_output_handle,
        .cpfd = nullptr,
    },



    {
        .uuid = &kHidInfoUuid.u,
        .access_cb = gatt_access,
        .arg = reinterpret_cast<void*>(static_cast<uintptr_t>(Attribute::HidInfo)),
        .descriptors = nullptr,
        .flags = BLE_GATT_CHR_F_READ,
        .min_key_size = 0,
        .val_handle = nullptr,
        .cpfd = nullptr,
    },
    {
        .uuid = &kControlPointUuid.u,
        .access_cb = gatt_access,
        .arg = reinterpret_cast<void*>(static_cast<uintptr_t>(Attribute::ControlPoint)),
        .descriptors = nullptr,
        .flags = BLE_GATT_CHR_F_WRITE_NO_RSP,
        .min_key_size = 0,
        .val_handle = nullptr,
        .cpfd = nullptr,
    },
    {
        .uuid = &kBootKeyboardInputUuid.u,
        .access_cb = gatt_access,
        .arg = reinterpret_cast<void*>(static_cast<uintptr_t>(Attribute::BootKeyboardInput)),
        .descriptors = nullptr,
        .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_NOTIFY,
        .min_key_size = 0,
        .val_handle = &g_boot_keyboard_input_handle,
        .cpfd = nullptr,
    },
    {
        .uuid = &kBootKeyboardOutputUuid.u,
        .access_cb = gatt_access,
        .arg = reinterpret_cast<void*>(static_cast<uintptr_t>(Attribute::BootKeyboardOutput)),
        .descriptors = nullptr,
        .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_WRITE | BLE_GATT_CHR_F_WRITE_NO_RSP,
        .min_key_size = 0,
        .val_handle = &g_boot_keyboard_output_handle,
        .cpfd = nullptr,
    },
    {},
};
const ble_gatt_svc_def kServices[] = {
    {
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = &kHidServiceUuid.u,
        .includes = nullptr,
        .characteristics = kCharacteristics,
    },
    {},
};
}  // namespace

namespace ble_keyboard_hid {
bool register_service() {
    int rc = ble_gatts_count_cfg(kServices);
    if (rc == 0) rc = ble_gatts_add_svcs(kServices);
    if (rc != 0) {
        ESP_LOGE(kTag, "keyboard service registration failed: rc=%d", rc);
        return false;
    }
    ESP_LOGI(kTag, "standard keyboard service registered: report=%u", kKeyboardReportId);
    return true;
}
}  // namespace ble_keyboard_hid
