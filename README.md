# Asyntai for Home Assistant

Your website's AI agent as a Home Assistant conversation agent.

[Asyntai](https://asyntai.com) answers your website visitors with everything it knows about your business: your pages, your documents, your products and your FAQs. This integration brings the same agent into Home Assistant. Ask it in the Assist dialog, on a voice satellite, or from an automation.

- Each Asyntai website becomes one conversation agent, named after the website.
- Follow-up questions keep the thread of the conversation.
- It answers in the language of the question.
- It uses the same knowledge base and AI instructions as your chat widget, so every channel says the same thing.

## Requirements

- Home Assistant 2025.4 or newer
- An Asyntai account on the Starter plan or higher (the integration uses the Asyntai API)

## Installation

### HACS

1. Open HACS, search for **Asyntai** and press **Download**.
2. Restart Home Assistant.

Until the integration is in the HACS default list, add it as a custom repository: in HACS open the menu, choose **Custom repositories**, add `https://github.com/asyntai/home-assistant-asyntai` with the type **Integration**, then download it.

### Manual

Copy `custom_components/asyntai` into the `custom_components` folder of your Home Assistant configuration and restart.

## Setup

1. In Asyntai, open **Settings**, then **API**, and copy your API key.
2. In Home Assistant, open **Settings**, **Devices & services**, press **Add integration** and choose **Asyntai**.
3. Paste the API key. If your account has several websites, choose the one whose knowledge should answer.
4. Open **Settings**, **Voice assistants**, edit an assistant and set **Conversation agent** to your website.

Add the integration once for each website to get one agent per website.

## Use in automations

```yaml
action: conversation.process
data:
  agent_id: conversation.your_website
  text: "What are your opening hours on Saturday?"
response_variable: answer
```

The answer is in `answer.response.speech.plain.speech`.

## Documentation

Full guide: https://asyntai.com/documentation/integrations/home-assistant/

## Support

Email hello@asyntai.com or open an issue in this repository.

## License

MIT
