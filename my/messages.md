SYSTEM:
You are a super-intelligent AI agent.
You were tasked with remotely controlling my multi-app mobile environment in order to solve my problem.

# MY PROBLEM
> I have a list of people I owe money to, including amounts and descriptions, in owe_list.csv. For each person, (1) If they have a Venmo account, send the money privately with the specified amount and description. (2) If not, create an individual (non-grouped) Splitwise expense with the same details so I remember to pay them later. For Splitwise expenses, attach the PDF receipt as well. They are in the same folder as the CSV file.

# INTERACTION WITH MY ENVIRONMENT
Tasks are carried out by remotely controlling my multi-app mobile environment.
The only way to remotely control my environment is using app-specific high-level API requests.

## APPS IN MY ENVIRONMENT
The environment contains the following apps:
- `supervisor`: An app to access supervisor's personal information, account credentials, addresses, payment cards, and manage the assigned task.
- `amazon`: An online shopping app to buy products and manage orders, returns, etc.
- `phone`: An app to find and manage contact information for friends, family members, etc., send and receive messages, and manage alarms.
- `file_system`: A file system app to create and manage files and folders.
- `spotify`: A music streaming app to stream songs and manage song, album and playlist libraries.
- `venmo`: A social payment app to send, receive and request money to and from others.
- `gmail`: An email app to draft, send, receive, and manage emails.
- `splitwise`: A bill splitting app to track and split expenses with people.
- `simple_note`: A note-taking app to create and manage notes
- `todoist`: A task management app to manage todo lists and collaborate on them with others.

## MY ENVIRONMENT VS YOUR ENVIRONMENT
My environment and your own local machine where the program runs are PHYSICALLY SEPARATED.
As a result:
1. Whenever the program needs to access my environment—such as reading data, writing data, or triggering actions inside an app—it must do so through the APIs exposed by the relevant apps.
2. Any operation performed locally on your machine, unless it invokes an app API, has no effect on my environment. In particular, file I/O through `os`, `open`, or similar libraries only accesses your machine's local file system, not my mobile environment.

# ABOUT ME
You are provided with the following GLOBAL variables about me, which you can access.
```python
# Global variables (available anywhere)
today: datetime = datetime.fromisoformat("2023-05-18T12:00:00") # today's date
my_name_first: str = "Lindsey" # my first name
my_name_last: str = "Simpson" # my last name
my_email: str = "lindseysimpson@gmail.com" # my email address
my_phone_number: str = "3567801924" # my phone number
```

# CORE OPERATING RULES IN SOLVING MY PROBLEM
You MUST strictly adhere to the following rules (R1, R2, R3 and R4) throughout the entire conversation.

## R1. DO NOT RELY ON HUMAN INTERVENTION IN ANY FORM
MY PROBLEM is 100% solvable on your own.
1. All apps and their APIs in my environment are fully functional. There is no chance that any API is broken, unavailable, or in need of my direct fix.
2. The information I have provided is fully sufficient to solve the problem, despite any initial appearance of ambiguity. All premises stated/required in my instruction are guaranteed to be true and valid. You can and must resolve any ambiguity, if any, by actively utilizing the available app APIs. In particular, referenced resources are accessible, specific conditions are checkable, constraints are satisfiable, and all outcomes/actions that my instruction intends you to do are attainable.

## R2. DO NOT RELY ON INVISIBLE ASSUMPTIONS
Never invent, guess, or hardcode values that are not explicitly provided in my instruction. In particular, if an API requires a specific parameter that is unknown to you, you MUST actively discover and ground it by utilizing the appropriate "read" or "search" APIs. Every value you use must be:
1. Explicitly visible in the provided information.
2. Already observed and confirmed by you during execution.
3. Directly retrieved from my environment using appropriate APIs.

## R3. DO NOT EXECUTE UNREQUESTED ACTIONS OR EXTRA BEHAVIORS
Be 100% faithful to my instruction.
1. Do NOT introduce extra behavior. Extra behavior refers to any supplementary logic—such as arbitrary data validation, logging, or exception handling—that is NOT explicitly requested.
2. Do NOT introduce unexpected state changes. If you intend to execute any "write" (not "read") action, you MUST review my instruction to ensure that it is explicitly requested. If it is not requested, you are on the wrong path.

## R4. DO NOT TREAT INFERENCES AS ABSOLUTE TRUTHS
Treat only MY PROBLEM statement and your grounded OBSERVATIONS as authoritative.
1. Anything derived during the solving process must remain provisional.
2. Any conclusion, interpretation, requirement, or structure DERIVED during the solving process must remain revisable in light of new, CONFIRMED EVIDENCE.
3. When new, confirmed evidence conflicts with an earlier derived view, update the view rather than forcing the evidence to fit it.

USER:
Your job is to explore my environment, by calling specific APIs one at a time, to gather enough contexts for implementing `main`.
Before proceeding, review the expected behavior of `main` and exploration process, then explicitly state your exact immediate exploration target.

```python
def main():
  access_token = get_file_system_access_token()
  directory_contents = file_system.show_directory(
    access_token=access_token["primary"],
    directory_path="~/",
    substring="owe_list.csv",
    entry_type="files",
    recursive=False,
  )
  print(f"access_token = {access_token}")
  print(f"directory_contents = {directory_contents}")
```

# EXPECTED FUNCTIONALITY (GUARANTEED SOLVABLE)
Process the user request. I have a list of people I owe money to, including amounts and descriptions, in owe_list.csv. For each person, (1) If they have a Venmo account, send the money privately with the specified amount and description. (2) If not, create an individual (non-grouped) Splitwise expense with the same details so I remember to pay them later. For Splitwise expenses, attach the PDF receipt as well. They are in the same folder as the CSV file.

# PRINTED LOCAL VARIABLES
access_token = {"primary": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJmaWxlX3N5c3RlbStsaW5kc2V5c2ltcHNvbkBnbWFpbC5jb20iLCJleHAiOjE2ODQ0MTI4MTR9.FKmsnbaLK_GsZCCBhXMgL1Pcy2Db3lQP6PSA_VWC8vk", "extras": {"token_type": "Bearer", "login_result": {"access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJmaWxlX3N5c3RlbStsaW5kc2V5c2ltcHNvbkBnbWFpbC5jb20iLCJleHAiOjE2ODQ0MTI4MTR9.FKmsnbaLK_GsZCCBhXMgL1Pcy2Db3lQP6PSA_VWC8vk", "token_type": "Bearer"}}}
directory_contents = []

# EXPLORATION PROCESS
We will proceed in repeated exploration rounds.
Each round is for choosing and executing exactly one API call.
In each round:
1. You select plausible candidate app(s). I will then list the APIs contained within those apps.
2. You select promising API(s) from that list. I will then provide their detailed specifications.
3. You inspect the API specs and decide which API(s), if any, truly qualify as potentially useful API to gather contexts.

ASSISTANT:
Understood. I will follow the exploration rounds to choose and execute one API call at a time in order to gather enough grounded context for implementing `main`.

# CURRENT EXPLORATION TARGET
The directory_contents is empty, meaning the file 'owe_list.csv' was not found in the root directory '~/'. I need to explore the file system to locate the correct directory path where 'owe_list.csv' and the associated PDF receipts are stored. The immediate exploration target is to list all directories and files in the file system to find the location of 'owe_list.csv'.

USER:
Since you have already invoked some APIs, decide whether to re-invoke one or more of them differently, or start a new exploration round to try a not-yet-tried API.

# PREVIOUSLY INVOKED APIs
Below are the specification of APIs you have already tried.
- `file_system.show_directory`: Show a list of files and/or sub-directories, optionally recursively, in a directory.
	- Parameters:
		- `access_token` (string, required): Access token obtained from file_system app login.
		- `directory_path` (string, optional): Path of the directory. Path can be absolute, starting with '/', or relative to the user's home directory, starting with '~/'. Default to /.
		- `substring` (string, optional): If passed, only files and sub-directories containing the given substring (ignoring case) will be shown. Default to None.
		- `entry_type` (string, optional): Whether to show all files and sub-directories, only files, or only sub-directories. Default to all.
		- `recursive` (boolean, optional): Whether to show files recursively. Default to True.

ASSISTANT:
Decided. The previous call to `file_system.show_directory` with `directory_path='~/'` and `substring='owe_list.csv'` returned an empty list. This could mean the file is not in the home directory, or the search parameters need adjustment. Since the problem states the file exists, I should re-invoke the same API but without the substring filter to see all contents of the home directory, or check the root directory. However, the most direct re-invoke is to list the home directory contents without filtering to understand the directory structure first.

# API TO RE-INVOKE
- file_system.show_directory

USER:
Inside `main`, re-invoke the API. Return a single Python function definition with the API call.

# PHASE 1: PREPARE ARGUMENTS (SETUP)
Before calling the target API, ensure every required parameter is ready.
- If a parameter's value is already available in GLOBAL, LOCAL, or WORKING MEMORY, use it directly.
- If a parameter's value is missing, you MUST create a variable for it by calling a new helper function first:
  - Call an unimplemented helper function to get the missing value. (The system will implement it later).
  - If necessary, pass only strictly visible and existing variables to this helper. Do NOT invent new context.
  - Assign the helper's return value to a local variable. Do NOT unpack or index this return value (assume it exactly matches the required type).

# PHASE 2: CALL TARGET API AND STOP (EXECUTION)
With all parameters prepared, invoke the target API.
- Call the API using the arguments prepared in Phase 1.
- Assign the result of an API call to a distinctly named local variable.
- You MUST stop coding immediately after this current body of `main`. Do NOT write any subsequent logic including any statement/expression. Your sole focus is to properly call the API and assign its return value to a local variable.

# COMMON MISTAKES
Review carefully to avoid:
1. Many APIs return items in "pages". Make sure to run through all the pages by looping over `page_index`.

# RESPONSE FORMAT
Return exactly ONE Python function definition containing your re-invoke.

```python
def main():
  ...
```

