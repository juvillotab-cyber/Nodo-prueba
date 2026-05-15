idf_component_register(SRCS "esp_ot_cli.c" "sensor_send.c"
                       INCLUDE_DIRS "."
                       PRIV_REQUIRES nvs_flash openthread)
