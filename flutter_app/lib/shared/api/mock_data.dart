import '../../features/room/models/conversation.dart';
import '../../features/today/models/today_card_model.dart';
import '../models/message.dart';
import '../models/room.dart';
import '../models/skill_info.dart';

/// All mock data for the v1 scaffold. Replace with real API calls in PR2.
///
/// Times are computed relative to a reference moment so the UI looks
/// reasonable on any launch day. Real timestamps come from the server.
class MockData {
  const MockData._();

  static DateTime get _now => DateTime(2026, 5, 22, 8, 15);

  // ---------------------------------------------------------------------------
  // Rooms
  // ---------------------------------------------------------------------------

  static const List<Room> rooms = [
    Room(
      id: 'claw-main',
      name: 'Claw Main',
      icon: 'C',
      subline: '12 skills, memory on, Obsidian indexed',
      isActive: true,
    ),
    Room(
      id: 'training',
      name: 'Training',
      icon: 'T',
      subline: 'Coming soon',
      isActive: false,
    ),
    Room(
      id: 'jessie',
      name: 'Jessie',
      icon: 'J',
      subline: 'Coming soon',
      isActive: false,
    ),
  ];

  static Room get activeRoom => rooms.firstWhere((r) => r.isActive);

  static Room? roomById(String id) {
    for (final room in rooms) {
      if (room.id == id) return room;
    }
    return null;
  }

  // ---------------------------------------------------------------------------
  // Today cards
  // ---------------------------------------------------------------------------

  static List<TodayCard> get todayCards => [
        TodayCard(
          id: 'card-morning-briefing',
          kind: TodayCardKind.morningBriefing,
          title: 'Morning briefing',
          subtitle: '6:47am',
          body:
              'Quick run today. Two SAGE quotes need closing follow-up before noon. '
              'FG board agenda lands in your inbox at 10. Weather is clear.',
          timestamp: _now.subtract(const Duration(hours: 1, minutes: 28)),
        ),
        TodayCard(
          id: 'card-weekly-review',
          kind: TodayCardKind.weeklyReview,
          title: 'Weekly review ready',
          subtitle: 'Sunday recap',
          body:
              'Last week, you closed 3 deals, ran 28 miles, and shipped PR5 (evals). '
              'Open the room to review and rate.',
          timestamp: _now.subtract(const Duration(days: 1)),
        ),
        TodayCard(
          id: 'card-low-rating',
          kind: TodayCardKind.lowRatingAlert,
          title: 'Claw Main rating dipped',
          subtitle: '7-day average 2.6',
          body:
              'Three of your last five responses were rated below 3. Worth reading the '
              'transcripts and noting what shifted.',
          timestamp: _now.subtract(const Duration(hours: 6)),
        ),
      ];

  // ---------------------------------------------------------------------------
  // Active conversation in Claw Main
  // ---------------------------------------------------------------------------

  static List<Message> get activeMessages => [
        Message(
          id: 'msg-1',
          role: MessageRole.user,
          body: 'What is on my plate before the FG board call?',
          timestamp: _now.subtract(const Duration(minutes: 20)),
        ),
        Message(
          id: 'msg-2',
          role: MessageRole.assistant,
          body:
              'Two quotes in SAGE that need follow-up by noon, and the FG board agenda '
              'review. I can pull both up.',
          timestamp: _now.subtract(const Duration(minutes: 19, seconds: 30)),
        ),
        Message(
          id: 'msg-3',
          role: MessageRole.user,
          body: 'Pull the SAGE quotes.',
          timestamp: _now.subtract(const Duration(minutes: 18)),
        ),
        Message(
          id: 'msg-4',
          role: MessageRole.toolCall,
          body: '',
          timestamp: _now.subtract(const Duration(minutes: 17, seconds: 45)),
          toolName: 'sage_connect.search_quotes',
          toolStatus: ToolCallStatus.inProgress,
          toolDetail: 'Searching SAGE for open quotes assigned to you',
        ),
        Message(
          id: 'msg-5',
          role: MessageRole.assistant,
          body:
              'Found two open quotes. Quote 4421 is waiting on artwork approval from the '
              'client. Quote 4438 needs a vendor response on lead time. Want the contact '
              'details for both?',
          timestamp: _now.subtract(const Duration(minutes: 17)),
        ),
      ];

  // ---------------------------------------------------------------------------
  // Skills loaded into Claw Main (Context tab)
  // ---------------------------------------------------------------------------

  static const List<SkillInfo> clawMainSkills = [
    SkillInfo(
      name: 'sage_connect.search_quotes',
      description: 'Search open SAGE quotes by client, status, or assignee.',
    ),
    SkillInfo(
      name: 'sage_connect.get_quote',
      description: 'Fetch full quote detail including artwork and vendor responses.',
    ),
    SkillInfo(
      name: 'hubspot.contact_lookup',
      description: 'Resolve a name or email to a HubSpot contact record.',
    ),
    SkillInfo(
      name: 'hubspot.deal_summary',
      description: 'Summarize deal stage, value, and recent activity.',
    ),
    SkillInfo(
      name: 'notion.fg_board_pages',
      description: 'Pull recent FG board agenda and minutes pages.',
    ),
    SkillInfo(
      name: 'obsidian.search_notes',
      description: 'Full-text search over the Obsidian vault.',
    ),
    SkillInfo(
      name: 'obsidian.read_note',
      description: 'Open a specific Obsidian note by path or title.',
    ),
    SkillInfo(
      name: 'gmail.recent_threads',
      description: 'List recent Gmail threads matching a query.',
    ),
    SkillInfo(
      name: 'gmail.draft_reply',
      description: 'Draft a reply on a specific thread, not sent automatically.',
    ),
    SkillInfo(
      name: 'findhelp.search_resources',
      description: 'Search Findhelp for local social services by zip and category.',
    ),
    SkillInfo(
      name: 'calendar.today',
      description: 'List today’s calendar events in priority order.',
    ),
    SkillInfo(
      name: 'memory.recall',
      description: 'Retrieve relevant past notes and preferences for this turn.',
    ),
  ];

  // ---------------------------------------------------------------------------
  // History (past conversations, date-grouped)
  // ---------------------------------------------------------------------------

  static List<Conversation> get history => [
        Conversation(
          id: 'conv-1',
          roomId: 'claw-main',
          preview: 'Plan the week before standup',
          startedAt: _now.subtract(const Duration(hours: 3)),
          messageCount: 14,
        ),
        Conversation(
          id: 'conv-2',
          roomId: 'claw-main',
          preview: 'Draft the SAGE follow-up email',
          startedAt: _now.subtract(const Duration(days: 1, hours: 4)),
          messageCount: 9,
        ),
        Conversation(
          id: 'conv-3',
          roomId: 'claw-main',
          preview: 'Compare merchandise vendor lead times',
          startedAt: _now.subtract(const Duration(days: 3)),
          messageCount: 22,
        ),
        Conversation(
          id: 'conv-4',
          roomId: 'claw-main',
          preview: 'Foster Greatness budget memo outline',
          startedAt: _now.subtract(const Duration(days: 6)),
          messageCount: 18,
        ),
        Conversation(
          id: 'conv-5',
          roomId: 'claw-main',
          preview: 'Ultra training mileage taper plan',
          startedAt: _now.subtract(const Duration(days: 18)),
          messageCount: 11,
        ),
      ];

  static Conversation? conversationById(String id) {
    for (final c in history) {
      if (c.id == id) return c;
    }
    return null;
  }
}
