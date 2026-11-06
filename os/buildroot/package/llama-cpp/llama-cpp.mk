################################################################################
# llama-cpp
################################################################################

LLAMA_CPP_VERSION = 74d4f5b041ad837153b0e90fc864b8290e01d8d5
LLAMA_CPP_SITE = $(call github,ggml-org,llama.cpp,$(LLAMA_CPP_VERSION))
LLAMA_CPP_LICENSE = MIT
LLAMA_CPP_LICENSE_FILES = LICENSE
LLAMA_CPP_CONF_OPTS = \
	-DBUILD_SHARED_LIBS=OFF \
	-DGGML_NATIVE=OFF \
	-DLLAMA_BUILD_TESTS=OFF \
	-DLLAMA_BUILD_EXAMPLES=ON \
	-DLLAMA_BUILD_SERVER=ON \
	-DLLAMA_CURL=OFF \
	-DLLAMA_SERVER_SSL=OFF
LLAMA_CPP_BUILD_OPTS = --target llama-server

define LLAMA_CPP_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/bin/llama-server $(TARGET_DIR)/usr/bin/llama-server
endef

$(eval $(cmake-package))
