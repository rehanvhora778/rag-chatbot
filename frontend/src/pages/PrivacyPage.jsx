import LegalLayout from '../components/landing/LegalLayout'

/**
 * Public privacy policy. Honest about what this academic RAG demo actually
 * stores (account details, uploaded documents, chat history) and the
 * third-party services it sends data to (Groq for generation).
 */
export default function PrivacyPage() {
  return (
    <LegalLayout
      title="Privacy Policy"
      updated="June 27, 2026"
      intro="This Privacy Policy explains what information RAG Chatbot collects when you create an account and use the app, how that information is used, and the choices you have. RAG Chatbot is an academic / portfolio project built to demonstrate Retrieval-Augmented Generation — it is not a commercial service."
      sections={[
        {
          heading: '1. Information we collect',
          body: ['We only collect what the app needs to function:'],
          list: [
            'Account details — your full name, username, email address, and a securely hashed password. We never store your password in plain text.',
            'Documents you upload — the files you add to your workspace are stored so they can be split into chunks, embedded, and searched when you ask questions.',
            'Chat activity — the questions you ask, the answers generated, and which document chunks were used as sources.',
            'Usage analytics — basic counts such as number of documents, queries, and sessions, used to power your dashboard and the analytics page.',
          ],
        },
        {
          heading: '2. How we use your information',
          list: [
            'To create and secure your account and keep you signed in.',
            'To process your documents into searchable embeddings and retrieve the most relevant passages for your questions.',
            'To generate answers grounded in your own documents.',
            'To show your personal usage statistics and improve the app.',
          ],
        },
        {
          heading: '3. Third-party services',
          body: [
            'To generate answers, the text of your question and the relevant retrieved passages from your documents are sent to our language-model provider (Groq) for processing. Their use of that data is governed by their own privacy policy.',
            'We do not sell your data, and we do not share it with advertisers.',
          ],
        },
        {
          heading: '4. Data storage & security',
          body: [
            'Your account data, documents, and chat history are stored in our database. Passwords are hashed, and access to the app is protected by authentication.',
            'Because this is a student / demonstration project, please do not upload confidential, sensitive, or regulated information.',
          ],
        },
        {
          heading: '5. Data retention & your choices',
          list: [
            'You can delete documents from your workspace at any time, which removes them and their associated embeddings.',
            'You can request deletion of your account and all associated data by emailing us.',
            'We keep your information only for as long as your account is active or as needed to run the app.',
          ],
        },
        {
          heading: '6. Children’s privacy',
          body: ['This project is not directed at children under 13, and we do not knowingly collect data from them.'],
        },
        {
          heading: '7. Changes to this policy',
          body: ['We may update this policy as the project evolves. Material changes will be reflected by the “Last updated” date above.'],
        },
      ]}
    />
  )
}
