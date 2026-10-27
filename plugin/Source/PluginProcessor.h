#pragma once

#include <JuceHeader.h>
#include <array>
#include <cmath>
#include <vector>

//==============================================================================
// Four small, self-contained DSP blocks.  They are original implementations
// inspired by the signal flow of the BandLab effects; they are not extracted
// from BandLab binaries and do not claim bit-exact parity.
//==============================================================================

class Biquad
{
public:
    void reset() noexcept { z1 = z2 = 0.0f; }

    void setLowShelf (double sampleRate, double freq, double gainDb, double shelfSlope = 1.0) noexcept
    {
        const double A = std::pow (10.0, gainDb / 40.0);
        const double w = 2.0 * juce::MathConstants<double>::pi * freq / sampleRate;
        const double cw = std::cos (w);
        const double sw = std::sin (w);
        const double alpha = sw * 0.5 * std::sqrt ((A + 1.0 / A) * (1.0 / shelfSlope - 1.0) + 2.0);
        const double beta = 2.0 * std::sqrt (A) * alpha;

        const double a0 = (A + 1.0) + (A - 1.0) * cw + beta;
        b0 = static_cast<float> (A * ((A + 1.0) - (A - 1.0) * cw + beta) / a0);
        b1 = static_cast<float> (2.0 * A * ((A - 1.0) - (A + 1.0) * cw) / a0);
        b2 = static_cast<float> (A * ((A + 1.0) - (A - 1.0) * cw - beta) / a0);
        a1 = static_cast<float> (-2.0 * ((A - 1.0) + (A + 1.0) * cw) / a0);
        a2 = static_cast<float> (((A + 1.0) + (A - 1.0) * cw - beta) / a0);
    }

    void setHighShelf (double sampleRate, double freq, double gainDb, double shelfSlope = 1.0) noexcept
    {
        const double A = std::pow (10.0, gainDb / 40.0);
        const double w = 2.0 * juce::MathConstants<double>::pi * freq / sampleRate;
        const double cw = std::cos (w);
        const double sw = std::sin (w);
        const double alpha = sw * 0.5 * std::sqrt ((A + 1.0 / A) * (1.0 / shelfSlope - 1.0) + 2.0);
        const double beta = 2.0 * std::sqrt (A) * alpha;

        const double a0 = (A + 1.0) - (A - 1.0) * cw + beta;
        b0 = static_cast<float> (A * ((A + 1.0) + (A - 1.0) * cw + beta) / a0);
        b1 = static_cast<float> (-2.0 * A * ((A - 1.0) + (A + 1.0) * cw) / a0);
        b2 = static_cast<float> (A * ((A + 1.0) + (A - 1.0) * cw - beta) / a0);
        a1 = static_cast<float> (2.0 * ((A - 1.0) - (A + 1.0) * cw) / a0);
        a2 = static_cast<float> (((A + 1.0) - (A - 1.0) * cw - beta) / a0);
    }

    void setPeak (double sampleRate, double freq, double gainDb, double q) noexcept
    {
        const double A = std::pow (10.0, gainDb / 40.0);
        const double w = 2.0 * juce::MathConstants<double>::pi * freq / sampleRate;
        const double cw = std::cos (w);
        const double alpha = std::sin (w) / (2.0 * q);

        const double a0 = 1.0 + alpha / A;
        b0 = static_cast<float> ((1.0 + alpha * A) / a0);
        b1 = static_cast<float> (-2.0 * cw / a0);
        b2 = static_cast<float> ((1.0 - alpha * A) / a0);
        a1 = static_cast<float> (-2.0 * cw / a0);
        a2 = static_cast<float> ((1.0 - alpha / A) / a0);
    }

    void setLowPass (double sampleRate, double freq, double q) noexcept
    {
        const double w = 2.0 * juce::MathConstants<double>::pi * freq / sampleRate;
        const double cw = std::cos (w);
        const double alpha = std::sin (w) / (2.0 * q);

        const double a0 = 1.0 + alpha;
        b0 = static_cast<float> ((1.0 - cw) * 0.5 / a0);
        b1 = static_cast<float> ((1.0 - cw) / a0);
        b2 = b0;
        a1 = static_cast<float> (-2.0 * cw / a0);
        a2 = static_cast<float> ((1.0 - alpha) / a0);
    }

    inline float process (float x) noexcept
    {
        const float y = b0 * x + z1;
        z1 = b1 * x - a1 * y + z2;
        z2 = b2 * x - a2 * y;
        return y;
    }

private:
    float b0 = 1.0f, b1 = 0.0f, b2 = 0.0f, a1 = 0.0f, a2 = 0.0f;
    float z1 = 0.0f, z2 = 0.0f;
};

//==============================================================================
class SpaceMakerReverb
{
public:
    void prepare (double sampleRate)
    {
        sr = sampleRate;
        const std::array<int, 4> primes { 1499, 1877, 2239, 2683 };
        const double scale = sr / 44100.0;

        for (size_t i = 0; i < lines.size(); ++i)
        {
            const int length = juce::jmax (64, static_cast<int> (primes[i] * scale));
            lines[i].assign (static_cast<size_t> (length), 0.0f);
            writeIndex[i] = 0;
            lowpass[i] = 0.0f;
        }

        preDelay.assign (static_cast<size_t> (juce::jmax (1, static_cast<int> (0.25 * sr))), 0.0f);
        preWrite = 0;
    }

    void reset()
    {
        for (auto& line : lines)
            std::fill (line.begin(), line.end(), 0.0f);
        std::fill (preDelay.begin(), preDelay.end(), 0.0f);
        lowpass.fill (0.0f);
        writeIndex.fill (0);
        preWrite = 0;
    }

    void process (float& left, float& right, float mix, float decaySeconds, float preDelayNorm, float damping) noexcept
    {
        if (mix <= 0.0001f)
            return;

        const float mono = 0.5f * (left + right);
        const int preSamples = juce::jlimit (1, static_cast<int> (preDelay.size()) - 1,
                                              static_cast<int> (preDelayNorm * 0.2f * static_cast<float> (sr)));
        preDelay[static_cast<size_t> (preWrite)] = mono;
        int readIndex = preWrite - preSamples;
        if (readIndex < 0)
            readIndex += static_cast<int> (preDelay.size());
        const float pre = preDelay[static_cast<size_t> (readIndex)];
        preWrite = (preWrite + 1) % static_cast<int> (preDelay.size());

        std::array<float, 4> out {};
        const float damp = juce::jlimit (0.0f, 0.85f, damping * 0.85f);

        for (size_t i = 0; i < lines.size(); ++i)
        {
            const float raw = lines[i][static_cast<size_t> (writeIndex[i])];
            lowpass[i] = raw * (1.0f - damp) + lowpass[i] * damp;
            out[i] = lowpass[i];
        }

        std::array<float, 4> mixed {};
        mixed[0] = 0.5f * (out[0] + out[1] + out[2] + out[3]);
        mixed[1] = 0.5f * (out[0] - out[1] + out[2] - out[3]);
        mixed[2] = 0.5f * (out[0] + out[1] - out[2] - out[3]);
        mixed[3] = 0.5f * (out[0] - out[1] - out[2] + out[3]);

        for (size_t i = 0; i < lines.size(); ++i)
        {
            const float delaySeconds = static_cast<float> (lines[i].size()) / static_cast<float> (sr);
            float gain = std::pow (10.0f, -3.0f * delaySeconds / juce::jmax (0.1f, decaySeconds));
            gain = juce::jlimit (0.0f, 0.995f, gain);
            lines[i][static_cast<size_t> (writeIndex[i])] = pre + mixed[i] * gain;
            writeIndex[i] = (writeIndex[i] + 1) % static_cast<int> (lines[i].size());
        }

        const float wetL = (out[0] - out[2]) * 0.70710678f;
        const float wetR = (out[1] - out[3]) * 0.70710678f;
        left = left * (1.0f - mix) + wetL * mix;
        right = right * (1.0f - mix) + wetR * mix;
    }

private:
    double sr = 44100.0;
    std::array<std::vector<float>, 4> lines;
    std::array<int, 4> writeIndex { 0, 0, 0, 0 };
    std::array<float, 4> lowpass { 0.0f, 0.0f, 0.0f, 0.0f };
    std::vector<float> preDelay;
    int preWrite = 0;
};

//==============================================================================
class DimensionBChorus
{
public:
    void prepare (double sampleRate)
    {
        sr = sampleRate;
        const int maxDelay = static_cast<int> (0.05 * sr) + 4;
        delayL.assign (static_cast<size_t> (maxDelay), 0.0f);
        delayR.assign (static_cast<size_t> (maxDelay), 0.0f);
        writePos = 0;
        phase = 0.0;
        lpL = lpR = 0.0f;
    }

    void reset()
    {
        std::fill (delayL.begin(), delayL.end(), 0.0f);
        std::fill (delayR.begin(), delayR.end(), 0.0f);
        writePos = 0;
        phase = 0.0;
        lpL = lpR = 0.0f;
    }

    void process (float& left, float& right, float modeNorm, float mix) noexcept
    {
        if (mix <= 0.0001f)
            return;

        const int mode = juce::jlimit (0, 3, static_cast<int> (modeNorm * 3.99f));
        constexpr float rates[4] { 0.45f, 0.55f, 0.75f, 1.10f };
        constexpr float depths[4] { 1.8f, 2.9f, 4.2f, 5.8f };

        phase += static_cast<double> (rates[mode]) / sr;
        if (phase >= 1.0)
            phase -= 1.0;

        const float tri = static_cast<float> (2.0 * std::abs (2.0 * (phase - std::floor (phase + 0.5))) - 1.0);
        const float centerMs = 7.0f;
        const float depthL = (centerMs + tri * depths[mode]) * 0.001f * static_cast<float> (sr);
        const float depthR = (centerMs - tri * depths[mode]) * 0.001f * static_cast<float> (sr);

        delayL[static_cast<size_t> (writePos)] = left;
        delayR[static_cast<size_t> (writePos)] = right;

        const float wetL = read (delayL, depthL);
        const float wetR = read (delayR, depthR);

        writePos = (writePos + 1) % static_cast<int> (delayL.size());

        lpL = 0.65f * wetL + 0.35f * lpL;
        lpR = 0.65f * wetR + 0.35f * lpR;

        left = left * (1.0f - 0.5f * mix) + lpL * mix;
        right = right * (1.0f - 0.5f * mix) + lpR * mix;
    }

private:
    float read (const std::vector<float>& buffer, float delaySamples) const noexcept
    {
        const int size = static_cast<int> (buffer.size());
        float position = static_cast<float> (writePos) - delaySamples;
        while (position < 0.0f)
            position += static_cast<float> (size);
        const int i0 = static_cast<int> (position) % size;
        const int i1 = (i0 + 1) % size;
        const float frac = position - std::floor (position);
        return buffer[static_cast<size_t> (i0)] * (1.0f - frac) + buffer[static_cast<size_t> (i1)] * frac;
    }

    double sr = 44100.0;
    std::vector<float> delayL, delayR;
    int writePos = 0;
    double phase = 0.0;
    float lpL = 0.0f, lpR = 0.0f;
};

//==============================================================================
class FeedbackCompressor
{
public:
    void prepare (double sampleRate)
    {
        sr = sampleRate;
        envelope = 0.0f;
        gain = 1.0f;
    }

    void reset()
    {
        envelope = 0.0f;
        gain = 1.0f;
    }

    void process (float& left, float& right, float squeeze, float attackNorm, float releaseNorm, float makeupNorm) noexcept
    {
        if (squeeze <= 0.0001f)
            return;

        const float attack = 0.0005f + attackNorm * 0.0495f;
        const float release = 0.030f + releaseNorm * 0.770f;
        const float attackCoeff = std::exp (-1.0f / (attack * static_cast<float> (sr)));
        const float releaseCoeff = std::exp (-1.0f / (release * static_cast<float> (sr)));

        const float outL = left * gain;
        const float outR = right * gain;

        const float detector = juce::jmax (std::abs (outL), std::abs (outR));
        const float coeff = detector > envelope ? attackCoeff : releaseCoeff;
        envelope = coeff * envelope + (1.0f - coeff) * detector;

        const float thresholdDb = -3.0f - squeeze * 33.0f;
        const float ratio = 1.5f + squeeze * 10.5f;
        const float levelDb = 20.0f * std::log10 (envelope + 1.0e-6f);

        float reductionDb = 0.0f;
        if (levelDb > thresholdDb)
            reductionDb = (thresholdDb - levelDb) * (1.0f - 1.0f / ratio);

        const float makeupDb = makeupNorm * 18.0f;
        gain = std::pow (10.0f, (reductionDb + makeupDb) / 20.0f);

        left = outL;
        right = outR;
    }

private:
    double sr = 44100.0;
    float envelope = 0.0f;
    float gain = 1.0f;
};

//==============================================================================
class GuitarAmp
{
public:
    void prepare (double sampleRate)
    {
        sr = sampleRate;
        updateTone (0.5f, 0.5f, 0.5f, 0.5f, 0.0f);
        lowShelf.reset();
        midPeak.reset();
        highShelf.reset();
        presenceShelf.reset();
        cabinet.reset();
    }

    void reset()
    {
        lowShelf.reset();
        midPeak.reset();
        highShelf.reset();
        presenceShelf.reset();
        cabinet.reset();
    }

    void updateTone (float bass, float mid, float treble, float presence, float cabModel) noexcept
    {
        lowShelf.setLowShelf (sr, 120.0, (bass - 0.5) * 24.0);
        midPeak.setPeak (sr, 850.0, (mid - 0.5) * 20.0, 1.2);
        highShelf.setHighShelf (sr, 3200.0, (treble - 0.5) * 24.0);
        presenceShelf.setHighShelf (sr, 4200.0, (presence - 0.5) * 12.0);

        constexpr double cutoffs[4] { 3600.0, 4800.0, 6000.0, 8000.0 };
        const int index = juce::jlimit (0, 3, static_cast<int> (cabModel * 3.99f));
        cabinet.setLowPass (sr, cutoffs[index], 0.707);
    }

    void process (juce::AudioBuffer<float>& buffer, float driveNorm) noexcept
    {
        if (driveNorm <= 0.0001f)
            return;

        const float drive = 1.0f + driveNorm * 25.0f;
        const float compensation = 1.0f / std::sqrt (drive);

        for (int channel = 0; channel < buffer.getNumChannels(); ++channel)
        {
            float* data = buffer.getWritePointer (channel);
            for (int i = 0; i < buffer.getNumSamples(); ++i)
            {
                const float in = data[i] * drive;
                float out = in >= 0.0f ? std::tanh (in) : std::tanh (in * 0.8f) * 1.15f;
                out *= compensation;
                out = highShelf.process (presenceShelf.process (midPeak.process (lowShelf.process (out))));
                data[i] = cabinet.process (out);
            }
        }
    }

private:
    double sr = 44100.0;
    Biquad lowShelf, midPeak, highShelf, presenceShelf, cabinet;
};

//==============================================================================
class BandLabWhiteBoxProcessor : public juce::AudioProcessor
{
public:
    BandLabWhiteBoxProcessor();
    ~BandLabWhiteBoxProcessor() override = default;

    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override {}
    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return "BandLab WhiteBox Suite"; }
    bool acceptsMidi() const override { return false; }
    bool producesMidi() const override { return false; }
    double getTailLengthSeconds() const override { return 4.0; }

    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram (int) override {}
    const juce::String getProgramName (int) override { return {}; }
    void changeProgramName (int, const juce::String&) override {}

    void getStateInformation (juce::MemoryBlock& destData) override;
    void setStateInformation (const void* data, int sizeInBytes) override;

    bool loadStateFile (const juce::File& file);
    juce::AudioProcessorValueTreeState apvts;

    static constexpr int numParams = 16;
    static const std::array<const char*, numParams>& parameterIds();

private:
    static juce::AudioProcessorValueTreeState::ParameterLayout createParameterLayout();

    SpaceMakerReverb reverb;
    DimensionBChorus chorus;
    FeedbackCompressor compressor;
    GuitarAmp amp;

    std::array<std::atomic<float>*, numParams> values {};

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (BandLabWhiteBoxProcessor)
};
