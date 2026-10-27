#include "PluginProcessor.h"
#include "PluginEditor.h"

#include <cstring>

namespace
{
constexpr std::array<const char*, 16> kParamIds {
    "rev_mix", "rev_decay", "rev_predelay", "rev_damping",
    "cho_mode", "cho_mix",
    "cmp_squeeze", "cmp_attack", "cmp_release", "cmp_makeup",
    "amp_drive", "amp_bass", "amp_mid", "amp_treble", "amp_presence", "amp_cab"
};

constexpr std::array<const char*, 16> kParamNames {
    "SpaceMaker Mix", "SpaceMaker Decay", "SpaceMaker PreDelay", "SpaceMaker Damping",
    "DimensionB Mode", "DimensionB Mix",
    "FBK Squeeze", "FBK Attack", "FBK Release", "FBK Makeup",
    "Amp Drive", "Amp Bass", "Amp Mid", "Amp Treble", "Amp Presence", "Amp Cab"
};

constexpr std::array<float, 16> kDefaults {
    0.0f, 0.35f, 0.1f, 0.4f,
    0.0f, 0.0f,
    0.0f, 0.2f, 0.4f, 0.2f,
    0.0f, 0.5f, 0.5f, 0.5f, 0.5f, 0.0f
};

#pragma pack(push, 1)
struct StateChunk
{
    char magic[4];
    juce::uint32 version;
    juce::uint32 activeMask;
    float params[16];
};
#pragma pack(pop)

static_assert (sizeof (StateChunk) == 76, "BLWB state chunk must stay 76 bytes");
} // namespace

const std::array<const char*, 16>& BandLabWhiteBoxProcessor::parameterIds()
{
    return kParamIds;
}

BandLabWhiteBoxProcessor::BandLabWhiteBoxProcessor()
    : AudioProcessor (BusesProperties()
                          .withInput ("Input", juce::AudioChannelSet::stereo(), true)
                          .withOutput ("Output", juce::AudioChannelSet::stereo(), true)),
      apvts (*this, nullptr, "PARAMETERS", createParameterLayout())
{
    for (size_t i = 0; i < values.size(); ++i)
        values[i] = apvts.getRawParameterValue (kParamIds[i]);
}

juce::AudioProcessorValueTreeState::ParameterLayout BandLabWhiteBoxProcessor::createParameterLayout()
{
    std::vector<std::unique_ptr<juce::RangedAudioParameter>> params;
    for (size_t i = 0; i < kParamIds.size(); ++i)
    {
        params.push_back (std::make_unique<juce::AudioParameterFloat>(
            juce::ParameterID { kParamIds[i], 1 },
            kParamNames[i],
            juce::NormalisableRange<float> (0.0f, 1.0f, 0.001f),
            kDefaults[i]));
    }
    return { params.begin(), params.end() };
}

void BandLabWhiteBoxProcessor::prepareToPlay (double sampleRate, int)
{
    reverb.prepare (sampleRate);
    chorus.prepare (sampleRate);
    compressor.prepare (sampleRate);
    amp.prepare (sampleRate);
}

void BandLabWhiteBoxProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer&)
{
    juce::ScopedNoDenormals noDenormals;
    const int numChannels = buffer.getNumChannels();
    if (numChannels == 0 || buffer.getNumSamples() == 0)
        return;

    const float revMix = values[0]->load();
    const float revDecay = 0.2f + values[1]->load() * 8.0f;
    const float revPre = values[2]->load();
    const float revDamp = values[3]->load();

    const float choMode = values[4]->load();
    const float choMix = values[5]->load();

    const float cmpSqueeze = values[6]->load();
    const float cmpAttack = values[7]->load();
    const float cmpRelease = values[8]->load();
    const float cmpMakeup = values[9]->load();

    const float ampDrive = values[10]->load();
    const float ampBass = values[11]->load();
    const float ampMid = values[12]->load();
    const float ampTreble = values[13]->load();
    const float ampPresence = values[14]->load();
    const float ampCab = values[15]->load();

    amp.updateTone (ampBass, ampMid, ampTreble, ampPresence, ampCab);
    amp.process (buffer, ampDrive);

    if (numChannels == 1)
    {
        float* channel = buffer.getWritePointer (0);
        for (int i = 0; i < buffer.getNumSamples(); ++i)
        {
            float left = channel[i];
            float right = left;
            compressor.process (left, right, cmpSqueeze, cmpAttack, cmpRelease, cmpMakeup);
            chorus.process (left, right, choMode, choMix);
            reverb.process (left, right, revMix, revDecay, revPre, revDamp);
            channel[i] = 0.5f * (left + right);
        }
        return;
    }

    float* leftChannel = buffer.getWritePointer (0);
    float* rightChannel = buffer.getWritePointer (1);
    for (int i = 0; i < buffer.getNumSamples(); ++i)
    {
        float left = leftChannel[i];
        float right = rightChannel[i];
        compressor.process (left, right, cmpSqueeze, cmpAttack, cmpRelease, cmpMakeup);
        chorus.process (left, right, choMode, choMix);
        reverb.process (left, right, revMix, revDecay, revPre, revDamp);
        leftChannel[i] = left;
        rightChannel[i] = right;
    }

    for (int channel = 2; channel < numChannels; ++channel)
        buffer.clear (channel, 0, buffer.getNumSamples());
}

juce::AudioProcessorEditor* BandLabWhiteBoxProcessor::createEditor()
{
    return new BandLabWhiteBoxEditor (*this);
}

void BandLabWhiteBoxProcessor::getStateInformation (juce::MemoryBlock& destData)
{
    StateChunk chunk {};
    std::memcpy (chunk.magic, "BLWB", 4);
    chunk.version = 1;
    chunk.activeMask = 0xFFFFFFFFu;
    for (size_t i = 0; i < values.size(); ++i)
        chunk.params[i] = juce::jlimit (0.0f, 1.0f, values[i]->load());

    destData.setSize (sizeof (StateChunk));
    std::memcpy (destData.getData(), &chunk, sizeof (StateChunk));
}

void BandLabWhiteBoxProcessor::setStateInformation (const void* data, int sizeInBytes)
{
    if (data == nullptr || sizeInBytes != static_cast<int> (sizeof (StateChunk)))
        return;

    StateChunk chunk {};
    std::memcpy (&chunk, data, sizeof (StateChunk));
    if (std::memcmp (chunk.magic, "BLWB", 4) != 0 || chunk.version != 1)
        return;

    for (size_t i = 0; i < values.size(); ++i)
    {
        if (auto* parameter = apvts.getParameter (kParamIds[i]))
            parameter->setValueNotifyingHost (juce::jlimit (0.0f, 1.0f, chunk.params[i]));
    }
}

bool BandLabWhiteBoxProcessor::loadStateFile (const juce::File& file)
{
    juce::MemoryBlock data;
    if (! file.loadFileAsData (data))
        return false;

    if (data.getSize() != sizeof (StateChunk))
        return false;

    setStateInformation (data.getData(), static_cast<int> (data.getSize()));
    return true;
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new BandLabWhiteBoxProcessor();
}
