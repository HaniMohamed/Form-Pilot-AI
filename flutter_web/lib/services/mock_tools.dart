/// Mock tool responses for simulating TOOL_CALL actions in the demo app.
///
/// In a real Flutter app, these tool calls would trigger actual API calls
/// or native functionality. Here we return hardcoded data for demo purposes.
library;

/// Simulates executing a tool call and returning mock data.
///
/// Returns a map with the tool result, or an error if the tool is unknown.
Map<String, dynamic> executeMockTool(
  String toolName, [
  Map<String, dynamic>? toolArgs,
]) {
  final handler = _mockToolHandlers[toolName];
  if (handler != null) {
    return handler(toolArgs ?? {});
  }
  return {'error': 'Unknown tool: $toolName'};
}

/// Map of tool names to their mock response handlers.
final Map<String, Map<String, dynamic> Function(Map<String, dynamic> args)>
    _mockToolHandlers = {
  'get_feature_flags': (_) => {
    'enableReportInjuryWithoutBottomSheet': false,
  },

  'get_establishments': (_) => {
    'establishments': [
      {
        'registrationNo': '5001234567',
        'name': {
          'english': 'Riyadh Technology Co.',
          'arabic': 'شركة تقنية الرياض',
        },
        'engagementType': 'regular',
        'ppaIndicator': false,
        'engagementPeriod': [
          {
            'startDate': '2022-01-15',
            'endDate': null,
            'occupation': 'Software Engineer',
          },
          {
            'startDate': '2020-06-01',
            'endDate': '2021-12-31',
            'occupation': 'Junior Developer',
          },
        ],
      },
      {
        'registrationNo': '5009876543',
        'name': {
          'english': 'Saudi Digital Solutions',
          'arabic': 'الحلول الرقمية السعودية',
        },
        'engagementType': 'regular',
        'ppaIndicator': false,
        'engagementPeriod': [
          {
            'startDate': '2023-03-01',
            'endDate': null,
            'occupation': 'Data Analyst',
          },
        ],
      },
    ],
  },

  'get_injury_types': (_) => {
    'types': [
      {'code': 'WI', 'value': {'english': 'Work Injury', 'arabic': 'إصابة عمل'}},
      {'code': 'OD', 'value': {'english': 'Occupational Disease', 'arabic': 'مرض مهني'}},
      {'code': 'RA', 'value': {'english': 'Road Accident (to/from work)', 'arabic': 'حادث طريق'}},
      {'code': 'WA', 'value': {'english': 'Workplace Accident', 'arabic': 'حادث في مكان العمل'}},
    ],
  },

  'get_injury_reasons': (args) {
    final typeName = args['typeName'] ?? args['injuryTypeEnglish'] ?? '';
    // Return different reasons based on injury type
    if (typeName.toString().contains('Road')) {
      return {
        'reasons': [
          {'code': 'R1', 'value': {'english': 'Traffic collision', 'arabic': 'تصادم مروري'}},
          {'code': 'R2', 'value': {'english': 'Vehicle malfunction', 'arabic': 'عطل في المركبة'}},
          {'code': 'R3', 'value': {'english': 'Road conditions', 'arabic': 'ظروف الطريق'}},
        ],
      };
    }
    return {
      'reasons': [
        {'code': 'R1', 'value': {'english': 'Slip or fall', 'arabic': 'انزلاق أو سقوط'}},
        {'code': 'R2', 'value': {'english': 'Equipment malfunction', 'arabic': 'عطل في المعدات'}},
        {'code': 'R3', 'value': {'english': 'Chemical exposure', 'arabic': 'تعرض كيميائي'}},
        {'code': 'R4', 'value': {'english': 'Heavy lifting', 'arabic': 'رفع أثقال'}},
        {'code': 'R5', 'value': {'english': 'Other', 'arabic': 'أخرى'}},
      ],
    };
  },

  'get_country_list': (_) => {
    'countries': [
      {'value': {'english': 'Saudi Arabia', 'arabic': 'المملكة العربية السعودية'}},
      {'value': {'english': 'United Arab Emirates', 'arabic': 'الإمارات العربية المتحدة'}},
      {'value': {'english': 'Bahrain', 'arabic': 'البحرين'}},
      {'value': {'english': 'Kuwait', 'arabic': 'الكويت'}},
      {'value': {'english': 'Oman', 'arabic': 'عمان'}},
      {'value': {'english': 'Qatar', 'arabic': 'قطر'}},
    ],
  },

  'get_required_documents': (args) => {
    'documents': [
      {'index': 0, 'name': 'Medical Report', 'required': true},
      {'index': 1, 'name': 'Police Report (if applicable)', 'required': false},
      {'index': 2, 'name': 'Witness Statement', 'required': false},
    ],
  },

  'set_field_value': (args) => {'success': true},

  'validate_step': (args) {
    final step = args['step'] ?? args['stepNumber'];
    return {'valid': true, 'step': step};
  },

  'show_location_picker': (_) => {
    'country': 'Saudi Arabia',
    'city': 'Riyadh',
    'address': 'King Fahd Road, Al Olaya District, Riyadh 12211',
    'latitude': 24.7136,
    'longitude': 46.6753,
  },

  'submit_injury_report': (_) => {
    'success': true,
    'injuryId': 'INJ-2026-001234',
  },

  'submit_emergency_contact': (args) => {'success': true},

  'upload_document': (args) => {
    'success': true,
    'fileName': 'medical_report_scan.pdf',
  },

  'remove_document': (args) => {'success': true},

  'submit_final': (_) => {
    'success': true,
    'referenceNumber': 'GOSI-REF-2026-567890',
  },
};
