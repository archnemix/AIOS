AIOS_KEYGEN_VERSION = 1
AIOS_KEYGEN_SITE = $(BR2_EXTERNAL_AIOS_PATH)/package/aios-keygen/src
AIOS_KEYGEN_SITE_METHOD = local
AIOS_KEYGEN_LICENSE = MIT

define AIOS_KEYGEN_BUILD_CMDS
	$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_LDFLAGS) -o $(@D)/aios-keygen $(@D)/keygen.c
endef

define AIOS_KEYGEN_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/aios-keygen $(TARGET_DIR)/usr/bin/aios-keygen
endef

$(eval $(generic-package))
