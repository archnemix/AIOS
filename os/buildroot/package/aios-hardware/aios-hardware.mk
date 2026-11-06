AIOS_HARDWARE_VERSION = 1
AIOS_HARDWARE_SITE = $(BR2_EXTERNAL_AIOS_PATH)/package/aios-hardware/src
AIOS_HARDWARE_SITE_METHOD = local
AIOS_HARDWARE_LICENSE = MIT

define AIOS_HARDWARE_BUILD_CMDS
	$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_LDFLAGS) -o $(@D)/aios-hardware $(@D)/hardware.c
endef

define AIOS_HARDWARE_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/aios-hardware $(TARGET_DIR)/usr/bin/aios-hardware
endef
$(eval $(generic-package))
