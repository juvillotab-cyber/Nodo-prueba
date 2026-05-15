#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#include "esp_err.h"
#include "esp_log.h"
#include "esp_openthread.h"
#include "esp_openthread_lock.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <openthread/error.h>
#include <openthread/instance.h>
#include <openthread/ip6.h>
#include <openthread/link.h>
#include <openthread/message.h>
#include <openthread/udp.h>

#include "sensor_send.h"

#define TAG "sensor_send"

#define SENSOR_TASK_STACK_SIZE 4096
#define SENSOR_SEND_INTERVAL_MS 10000
#define SENSOR_DEST_PORT 5689
#define SENSOR_DEST_ADDR "ff03::1"

static bool has_thread_address(otInstance *instance)
{
    for (const otNetifAddress *addr = otIp6GetUnicastAddresses(instance); addr; addr = addr->mNext) {
        if (addr->mAddressOrigin == OT_ADDRESS_ORIGIN_THREAD) {
            return true;
        }
    }
    return false;
}

static void sensor_send_task(void *arg)
{
    otInstance *instance = (otInstance *)arg;
    char buf[128];
    char node_id[24];
    int seq = 0;

    {
        const otExtAddress *extaddr = otLinkGetExtendedAddress(instance);
        snprintf(node_id, sizeof(node_id),
            "%02x%02x%02x%02x%02x%02x%02x%02x",
            extaddr->m8[0], extaddr->m8[1], extaddr->m8[2], extaddr->m8[3],
            extaddr->m8[4], extaddr->m8[5], extaddr->m8[6], extaddr->m8[7]);
    }

    ESP_LOGI(TAG, "started, node_id=%s, destination: %s:%d", node_id, SENSOR_DEST_ADDR, SENSOR_DEST_PORT);

    while (!has_thread_address(instance)) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
    ESP_LOGI(TAG, "Thread ready, sending every %d ms", SENSOR_SEND_INTERVAL_MS);

    while (1) {
        float temp = 25.0f + ((float)esp_random() / (float)UINT32_MAX) * 5.0f;

        int len = snprintf(buf, sizeof(buf),
            "{\"node_id\":\"%s\",\"seq\":%d,\"temp\":%.1f}",
            node_id, seq++, temp);

        otMessageInfo messageInfo;
        memset(&messageInfo, 0, sizeof(messageInfo));
        if (otIp6AddressFromString(SENSOR_DEST_ADDR, &messageInfo.mPeerAddr) != OT_ERROR_NONE) {
            ESP_LOGE(TAG, "invalid address: %s", SENSOR_DEST_ADDR);
            vTaskDelay(pdMS_TO_TICKS(SENSOR_SEND_INTERVAL_MS));
            continue;
        }
        messageInfo.mPeerPort = SENSOR_DEST_PORT;
        messageInfo.mHopLimit = 64;

        esp_openthread_lock_acquire(portMAX_DELAY);

        otMessage *message = otUdpNewMessage(instance, NULL);
        if (message) {
            otError append_error = otMessageAppend(message, buf, len);
            if (append_error != OT_ERROR_NONE) {
                ESP_LOGE(TAG, "append: %s", otThreadErrorToString(append_error));
                otMessageFree(message);
            } else {
                otError send_error = otUdpSendDatagram(instance, message, &messageInfo);
                if (send_error == OT_ERROR_NONE) {
                    ESP_LOGI(TAG, "sent: %s", buf);
                } else {
                    ESP_LOGE(TAG, "send: %s", otThreadErrorToString(send_error));
                    otMessageFree(message);
                }
            }
        }

        esp_openthread_lock_release();

        vTaskDelay(pdMS_TO_TICKS(SENSOR_SEND_INTERVAL_MS));
    }
}

void sensor_send_init(otInstance *instance)
{
    xTaskCreate(sensor_send_task, "sensor_send", SENSOR_TASK_STACK_SIZE,
                instance, 5, NULL);
}
