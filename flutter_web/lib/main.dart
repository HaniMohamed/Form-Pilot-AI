import 'package:flutter/material.dart';

import 'screens/simulation_screen.dart';

void main() {
  runApp(const FormPilotApp());
}

/// Root widget for the FormPilot AI simulation and testing app.
class FormPilotApp extends StatelessWidget {
  const FormPilotApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'FormPilot AI',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF1A73E8),
        useMaterial3: true,
        brightness: Brightness.light,
      ),
      home: const SimulationScreen(),
    );
  }
}
