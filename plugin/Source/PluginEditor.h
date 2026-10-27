#pragma once

#include <JuceHeader.h>
#include "PluginProcessor.h"

class BandLabLookAndFeel : public juce::LookAndFeel_V4
{
public:
    BandLabLookAndFeel()
    {
        setColour (juce::Slider::rotarySliderFillColourId, juce::Colour (0xFFFF385C));
        setColour (juce::Slider::rotarySliderOutlineColourId, juce::Colour (0xFF323842));
        setColour (juce::Slider::thumbColourId, juce::Colours::white);
        setColour (juce::TextButton::buttonColourId, juce::Colour (0xFF23272E));
        setColour (juce::Label::textColourId, juce::Colour (0xFFC9D1DE));
    }

    void drawRotarySlider (juce::Graphics& g,
                           int x, int y, int width, int height,
                           float sliderPos,
                           float rotaryStartAngle,
                           float rotaryEndAngle,
                           juce::Slider&) override
    {
        const float radius = static_cast<float> (juce::jmin (width / 2, height / 2)) - 6.0f;
        const float centreX = static_cast<float> (x) + static_cast<float> (width) * 0.5f;
        const float centreY = static_cast<float> (y) + static_cast<float> (height) * 0.5f;
        const float angle = rotaryStartAngle + sliderPos * (rotaryEndAngle - rotaryStartAngle);

        g.setColour (juce::Colour (0xFF1E2229));
        g.fillEllipse (centreX - radius, centreY - radius, radius * 2.0f, radius * 2.0f);

        juce::Path background;
        background.addCentredArc (centreX, centreY, radius, radius, 0.0f,
                                  rotaryStartAngle, rotaryEndAngle, true);
        g.setColour (juce::Colour (0xFF323842));
        g.strokePath (background, juce::PathStrokeType (3.0f, juce::PathStrokeType::curved,
                                                        juce::PathStrokeType::rounded));

        juce::Path value;
        value.addCentredArc (centreX, centreY, radius, radius, 0.0f,
                             rotaryStartAngle, angle, true);
        g.setColour (juce::Colour (0xFFFF385C));
        g.strokePath (value, juce::PathStrokeType (3.0f, juce::PathStrokeType::curved,
                                                   juce::PathStrokeType::rounded));

        juce::Path pointer;
        pointer.addRectangle (-1.5f, -radius, 3.0f, radius * 0.62f);
        pointer.applyTransform (juce::AffineTransform::rotation (angle).translated (centreX, centreY));
        g.setColour (juce::Colours::white);
        g.fillPath (pointer);
    }
};

class BandLabWhiteBoxEditor : public juce::AudioProcessorEditor
{
public:
    explicit BandLabWhiteBoxEditor (BandLabWhiteBoxProcessor&);
    ~BandLabWhiteBoxEditor() override;

    void paint (juce::Graphics&) override;
    void resized() override;

private:
    struct Knob
    {
        std::unique_ptr<juce::Slider> slider;
        std::unique_ptr<juce::Label> label;
        std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment> attachment;
    };

    void addKnob (int index, const juce::String& title);
    void loadStateFile();
    juce::Rectangle<int> cardBounds (int index) const;

    BandLabWhiteBoxProcessor& processor;
    BandLabLookAndFeel lookAndFeel;
    std::array<Knob, BandLabWhiteBoxProcessor::numParams> knobs;
    juce::TextButton loadButton { "Load .blwb state" };
    std::unique_ptr<juce::FileChooser> chooser;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (BandLabWhiteBoxEditor)
};
