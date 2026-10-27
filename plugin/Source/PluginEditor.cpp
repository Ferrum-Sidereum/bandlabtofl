#include "PluginEditor.h"

namespace
{
constexpr std::array<const char*, 4> kCardTitles {
    "SPACE MAKER - FDN REVERB",
    "DIMENSION B - BBD CHORUS",
    "FBK OPTICAL COMPRESSOR",
    "GUITAR AMP - TONE STACK"
};

constexpr std::array<const char*, 16> kKnobTitles {
    "Mix", "Decay", "PreDelay", "Damping",
    "Mode", "Mix",
    "Squeeze", "Attack", "Release", "Makeup",
    "Drive", "Bass", "Mid", "Treble", "Presence", "Cab"
};

constexpr std::array<int, 4> kCardKnobs { 4, 2, 4, 6 };
constexpr std::array<int, 4> kCardFirst { 0, 4, 6, 10 };
} // namespace

BandLabWhiteBoxEditor::BandLabWhiteBoxEditor (BandLabWhiteBoxProcessor& p)
    : AudioProcessorEditor (&p), processor (p)
{
    setLookAndFeel (&lookAndFeel);

    for (int i = 0; i < BandLabWhiteBoxProcessor::numParams; ++i)
        addKnob (i, kKnobTitles[static_cast<size_t> (i)]);

    addAndMakeVisible (loadButton);
    loadButton.onClick = [this] { loadStateFile(); };

    setResizable (true, true);
    setResizeLimits (760, 460, 1400, 900);
    setSize (880, 520);
}

BandLabWhiteBoxEditor::~BandLabWhiteBoxEditor()
{
    setLookAndFeel (nullptr);
}

void BandLabWhiteBoxEditor::addKnob (int index, const juce::String& title)
{
    auto& knob = knobs[static_cast<size_t> (index)];
    knob.slider = std::make_unique<juce::Slider> (juce::Slider::RotaryHorizontalVerticalDrag,
                                                  juce::Slider::TextBoxBelow);
    knob.slider->setTextBoxStyle (juce::Slider::TextBoxBelow, false, 62, 16);
    addAndMakeVisible (*knob.slider);

    knob.label = std::make_unique<juce::Label> ("", title);
    knob.label->setJustificationType (juce::Justification::centred);
    knob.label->setFont (juce::Font (juce::FontOptions (12.0f).withStyle ("Bold")));
    addAndMakeVisible (*knob.label);

    knob.attachment = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (
        processor.apvts, BandLabWhiteBoxProcessor::parameterIds()[static_cast<size_t> (index)],
        *knob.slider);
}

juce::Rectangle<int> BandLabWhiteBoxEditor::cardBounds (int index) const
{
    const int margin = 16;
    const int gap = 12;
    const int cardWidth = (getWidth() - margin * 2 - gap) / 2;
    const int cardHeight = (getHeight() - 86 - margin - gap) / 2;
    const int column = index % 2;
    const int row = index / 2;
    return { margin + column * (cardWidth + gap), 70 + row * (cardHeight + gap),
             cardWidth, cardHeight };
}

void BandLabWhiteBoxEditor::paint (juce::Graphics& g)
{
    g.fillAll (juce::Colour (0xFF121417));

    g.setColour (juce::Colour (0xFF1B1E24));
    g.fillRect (0, 0, getWidth(), 58);

    g.setColour (juce::Colour (0xFFFF385C));
    g.setFont (juce::Font (juce::FontOptions (19.0f).withStyle ("Bold")));
    g.drawText ("BANDLAB WHITEBOX SUITE", 18, 9, 520, 26, juce::Justification::centredLeft);

    g.setColour (juce::Colour (0xFF6F7A8B));
    g.setFont (juce::Font (juce::FontOptions (11.0f)));
    g.drawText ("modelled effects - not bit-exact BandLab DSP", 18, 32, 520, 18,
                juce::Justification::centredLeft);

    for (int card = 0; card < 4; ++card)
    {
        const auto bounds = cardBounds (card).toFloat();
        g.setColour (juce::Colour (0xFF1A1D24));
        g.fillRoundedRectangle (bounds, 8.0f);
        g.setColour (juce::Colour (0xFF2B303C));
        g.drawRoundedRectangle (bounds, 8.0f, 1.0f);

        g.setColour (juce::Colour (0xFF9AA4B5));
        g.setFont (juce::Font (juce::FontOptions (11.0f).withStyle ("Bold")));
        g.drawText (kCardTitles[static_cast<size_t> (card)],
                    cardBounds (card).removeFromTop (24).reduced (10, 4),
                    juce::Justification::centredLeft);
    }
}

void BandLabWhiteBoxEditor::resized()
{
    loadButton.setBounds (getWidth() - 190, 14, 172, 28);

    for (int card = 0; card < 4; ++card)
    {
        const auto bounds = cardBounds (card);
        const int count = kCardKnobs[static_cast<size_t> (card)];
        const int first = kCardFirst[static_cast<size_t> (card)];
        const auto inner = bounds.reduced (8).withTrimmedTop (24);
        const int knobWidth = inner.getWidth() / count;

        for (int slot = 0; slot < count; ++slot)
        {
            auto& knob = knobs[static_cast<size_t> (first + slot)];
            const int x = inner.getX() + slot * knobWidth;
            knob.label->setBounds (x, inner.getY(), knobWidth, 16);
            knob.slider->setBounds (x, inner.getY() + 14, knobWidth,
                                    juce::jmin (inner.getHeight() - 14, 132));
        }
    }
}

void BandLabWhiteBoxEditor::loadStateFile()
{
    chooser = std::make_unique<juce::FileChooser> (
        "Load a .blwb state written by BL2FLP",
        juce::File::getSpecialLocation (juce::File::userDocumentsDirectory),
        "*.blwb");

    chooser->launchAsync (juce::FileBrowserComponent::openMode
                              | juce::FileBrowserComponent::canSelectFiles,
                          [this] (const juce::FileChooser& fc)
                          {
                              const auto file = fc.getResult();
                              if (file.existsAsFile() && ! processor.loadStateFile (file))
                              {
                                  juce::AlertWindow::showMessageBoxAsync (
                                      juce::MessageBoxIconType::WarningIcon,
                                      "BL2FLP",
                                      "The selected file is not a valid 76-byte .blwb state.");
                              }
                          });
}
