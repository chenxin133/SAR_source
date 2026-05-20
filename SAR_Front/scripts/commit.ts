import { execSync } from 'child_process';
import * as readline from 'readline';

const types = [
  'feat',     // New feature
  'fix',      // Bug fix
  'docs',     // Documentation only changes
  'style',    // Changes that do not affect the meaning of the code (white-space, formatting, etc)
  'refactor', // A code change that neither fixes a bug nor adds a feature
  'perf',     // A code change that improves performance
  'test',     // Adding missing tests or correcting existing tests
  'build',    // Changes that affect the build system or external dependencies
  'ci',       // Changes to our CI configuration files and scripts
  'chore',    // Other changes that don't modify src or test files
  'revert',   // Reverts a previous commit
];

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

const ask = (question: string): Promise<string> => {
  return new Promise((resolve) => {
    rl.question(question, (answer) => {
      resolve(answer.trim());
    });
  });
};

const run = async () => {
  console.log('--- Standardized Git Commit Wizard ---\n');

  // 1. Select Type
  console.log('Select the type of change that you\'re committing:');
  types.forEach((t, i) => console.log(`${i + 1}. ${t}`));
  
  let typeIndex = -1;
  while (typeIndex < 0 || typeIndex >= types.length) {
    const answer = await ask(`Choose type (1-${types.length}): `);
    const n = parseInt(answer, 10);
    if (!isNaN(n) && n >= 1 && n <= types.length) {
      typeIndex = n - 1;
    } else {
        // Allow typing the name directly if valid
        const index = types.indexOf(answer);
        if (index !== -1) typeIndex = index;
    }
  }
  const type = types[typeIndex];

  // 2. Scope
  const scope = await ask('Enter the scope of this change (optional): ');

  // 3. Subject
  let subject = '';
  while (!subject) {
    subject = await ask('Write a short, imperative tense description of the change:\n');
  }

  // 4. Body
  const body = await ask('Provide a longer description of the change (optional). Press Enter to skip:\n');

  // 5. Footer
  const footer = await ask('List any breaking changes or issues closed by this change (optional). Press Enter to skip:\n');

  // Construct message
  let message = `${type}${scope ? `(${scope})` : ''}: ${subject}`;
  if (body) {
    message += `\n\n${body}`;
  }
  if (footer) {
    message += `\n\n${footer}`;
  }

  console.log('\n--- Commit Message Preview ---');
  console.log(message);
  console.log('------------------------------\n');

  const confirm = await ask('Proceed with commit? (y/n): ');
  if (confirm.toLowerCase() === 'y' || confirm.toLowerCase() === 'yes') {
    try {
      console.log('Staging all changes...');
      execSync('git add .', { stdio: 'inherit' });
      console.log('Committing...');
      // Escape double quotes in message for shell command
      const escapedMessage = message.replace(/"/g, '\\"');
      execSync(`git commit -m "${escapedMessage}"`, { stdio: 'inherit' });
      console.log('Commit successful!');
    } catch (error) {
      console.error('Commit failed:', error);
    }
  } else {
    console.log('Commit aborted.');
  }

  rl.close();
};

run();
