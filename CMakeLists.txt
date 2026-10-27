cmake_minimum_required(VERSION 3.22)
project(BandLabWhiteBox VERSION 0.1.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_subdirectory(vendor/JUCE)

juce_add_plugin(BandLabWhiteBox
    COMPANY_NAME "WhiteBoxAudio"
    IS_SYNTH FALSE
    NEEDS_MIDI_INPUT FALSE
    NEEDS_MIDI_OUTPUT FALSE
    IS_MIDI_EFFECT FALSE
    EDITOR_WANTS_KEYBOARD_FOCUS FALSE
    COPY_PLUGIN_AFTER_BUILD FALSE
    PLUGIN_MANUFACTURER_CODE WbAu
    PLUGIN_CODE BlWb
    FORMATS VST3 Standalone
    PRODUCT_NAME "BandLab WhiteBox Suite")

juce_generate_juce_header(BandLabWhiteBox)

target_sources(BandLabWhiteBox PRIVATE
    plugin/Source/PluginProcessor.cpp
    plugin/Source/PluginEditor.cpp)

target_include_directories(BandLabWhiteBox PRIVATE plugin/Source)

target_compile_definitions(BandLabWhiteBox PUBLIC
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_VST3_CAN_REPLACE_VST2=0)

target_link_libraries(BandLabWhiteBox PRIVATE
    juce::juce_audio_utils
    juce::juce_dsp
    PUBLIC
    juce::juce_recommended_config_flags
    juce::juce_recommended_lto_flags
    juce::juce_recommended_warning_flags)
