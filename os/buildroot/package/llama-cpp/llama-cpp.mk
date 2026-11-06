################################################################################
# llama-cpp
################################################################################

LLAMA_CPP_VERSION = 74d4f5b041ad837153b0e90fc864b8290e01d8d5
LLAMA_CPP_SITE = $(call github,ggml-org,llama.cpp,$(LLAMA_CPP_VERSION))
LLAMA_CPP_LICENSE = MIT
LLAMA_CPP_LICENSE_FILES = LICENSE
LLAMA_CPP_SUPPORTS_IN_SOURCE_BUILD = NO
LLAMA_CPP_CONF_OPTS = \
	-DBUILD_SHARED_LIBS=OFF \
	-DGGML_NATIVE=OFF \
	-DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_FMA=OFF -DGGML_F16C=OFF -DGGML_BMI2=OFF \
	-DGGML_AVX_VNNI=OFF -DGGML_AVX512=OFF -DGGML_AVX512_VBMI=OFF \
	-DGGML_AVX512_VNNI=OFF -DGGML_AVX512_BF16=OFF \
	-DLLAMA_BUILD_TESTS=OFF \
	-DLLAMA_BUILD_EXAMPLES=ON \
	-DLLAMA_BUILD_SERVER=ON \
	-DLLAMA_CURL=OFF \
	-DLLAMA_SERVER_SSL=OFF
LLAMA_CPP_BUILD_OPTS = --target llama-server llama-bench

# Upstream b5046 unconditionally enables SSE4.2 for non-native GCC builds.
# Remove that assumption so the fallback works on baseline x86-64 CPUs.
define LLAMA_CPP_ALLOW_BASELINE_X86_64
	sed -i '/list(APPEND ARCH_FLAGS -msse4.2)/d; /list(APPEND ARCH_DEFINITIONS GGML_SSE42)/d' $(@D)/ggml/src/ggml-cpu/CMakeLists.txt
endef
LLAMA_CPP_POST_PATCH_HOOKS += LLAMA_CPP_ALLOW_BASELINE_X86_64

# A second, explicitly targeted build keeps the portable server available for
# CPUs that cannot execute AVX2. Runtime selection is deliberately conservative.
define LLAMA_CPP_CONFIGURE_AVX2
	PATH=$(BR_PATH) $(BR2_CMAKE) -S $(@D) -B $(@D)/buildroot-avx2 \
		-DCMAKE_TOOLCHAIN_FILE="$(HOST_DIR)/share/buildroot/toolchainfile.cmake" \
		-DCMAKE_INSTALL_PREFIX=/usr $(LLAMA_CPP_CONF_OPTS) \
		-DGGML_AVX=ON -DGGML_AVX2=ON -DGGML_FMA=ON -DGGML_F16C=ON -DGGML_BMI2=ON
endef
LLAMA_CPP_POST_CONFIGURE_HOOKS += LLAMA_CPP_CONFIGURE_AVX2

define LLAMA_CPP_BUILD_AVX2
	$(TARGET_MAKE_ENV) $(BR2_CMAKE) --build $(@D)/buildroot-avx2 -j$(PARALLEL_JOBS) --target llama-server llama-bench
endef
LLAMA_CPP_POST_BUILD_HOOKS += LLAMA_CPP_BUILD_AVX2

define LLAMA_CPP_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/buildroot-build/bin/llama-server $(TARGET_DIR)/usr/bin/llama-server
	$(INSTALL) -D -m 0755 $(@D)/buildroot-avx2/bin/llama-server $(TARGET_DIR)/usr/bin/llama-server-avx2
	$(INSTALL) -D -m 0755 $(@D)/buildroot-build/bin/llama-bench $(TARGET_DIR)/usr/bin/llama-bench
	$(INSTALL) -D -m 0755 $(@D)/buildroot-avx2/bin/llama-bench $(TARGET_DIR)/usr/bin/llama-bench-avx2
endef

$(eval $(cmake-package))
