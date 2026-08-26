export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[];

export type Database = {
  graphql_public: {
    Tables: {
      [_ in never]: never;
    };
    Views: {
      [_ in never]: never;
    };
    Functions: {
      graphql: {
        Args: {
          extensions?: Json;
          operationName?: string;
          query?: string;
          variables?: Json;
        };
        Returns: Json;
      };
    };
    Enums: {
      [_ in never]: never;
    };
    CompositeTypes: {
      [_ in never]: never;
    };
  };
  public: {
    Tables: {
      [_ in never]: never;
    };
    Views: {
      vw_deviation_by_employee_day: {
        Row: {
          employee_id: string | null;
          employee_name: string | null;
          eventos: number | null;
          minutes_abs: number | null;
          reference_date: string | null;
          tenant_id: string | null;
          unit_id: string | null;
          unit_name: string | null;
        };
        Relationships: [
          {
            foreignKeyName: "deviation_event_employee_id_fkey";
            columns: ["employee_id"];
            isOneToOne: false;
            referencedRelation: "vw_employee";
            referencedColumns: ["employee_id"];
          },
          {
            foreignKeyName: "deviation_event_unit_id_fkey";
            columns: ["unit_id"];
            isOneToOne: false;
            referencedRelation: "vw_unit";
            referencedColumns: ["unit_id"];
          },
        ];
      };
      vw_deviation_daily_trend: {
        Row: {
          direction: string | null;
          eventos: number | null;
          minutes_abs: number | null;
          reference_date: string | null;
          tenant_id: string | null;
          unit_id: string | null;
        };
        Relationships: [
          {
            foreignKeyName: "deviation_event_unit_id_fkey";
            columns: ["unit_id"];
            isOneToOne: false;
            referencedRelation: "vw_unit";
            referencedColumns: ["unit_id"];
          },
        ];
      };
      vw_deviation_event: {
        Row: {
          actual_time: string | null;
          category: string | null;
          company_id: string | null;
          counts_as_deviation: boolean | null;
          detected_at: string | null;
          direction: string | null;
          employee_id: string | null;
          employee_name: string | null;
          evento_id: string | null;
          expected_time: string | null;
          minutes: number | null;
          minutes_abs: number | null;
          pendente_de_ciclo: boolean | null;
          reference_date: string | null;
          report_cycle_id: string | null;
          status: string | null;
          tenant_id: string | null;
          type: string | null;
          type_description: string | null;
          unit_id: string | null;
          unit_name: string | null;
        };
        Relationships: [
          {
            foreignKeyName: "deviation_event_employee_id_fkey";
            columns: ["employee_id"];
            isOneToOne: false;
            referencedRelation: "vw_employee";
            referencedColumns: ["employee_id"];
          },
          {
            foreignKeyName: "deviation_event_unit_id_fkey";
            columns: ["unit_id"];
            isOneToOne: false;
            referencedRelation: "vw_unit";
            referencedColumns: ["unit_id"];
          },
        ];
      };
      vw_deviation_summary_by_unit: {
        Row: {
          colaboradores: number | null;
          company_id: string | null;
          eventos: number | null;
          minutes_abs: number | null;
          minutes_excedente: number | null;
          minutes_faltante: number | null;
          reference_date: string | null;
          tenant_id: string | null;
          unit_id: string | null;
          unit_name: string | null;
        };
        Relationships: [
          {
            foreignKeyName: "deviation_event_unit_id_fkey";
            columns: ["unit_id"];
            isOneToOne: false;
            referencedRelation: "vw_unit";
            referencedColumns: ["unit_id"];
          },
        ];
      };
      vw_document_expiry: {
        Row: {
          dias_para_vencer: number | null;
          document_id: string | null;
          em_alerta: boolean | null;
          employee_id: string | null;
          employee_name: string | null;
          expiry_alert_days: number | null;
          tenant_id: string | null;
          type_name: string | null;
          unit_id: string | null;
          valid_until: string | null;
        };
        Relationships: [
          {
            foreignKeyName: "document_employee_id_fkey";
            columns: ["employee_id"];
            isOneToOne: false;
            referencedRelation: "vw_employee";
            referencedColumns: ["employee_id"];
          },
          {
            foreignKeyName: "employee_unit_id_fkey";
            columns: ["unit_id"];
            isOneToOne: false;
            referencedRelation: "vw_unit";
            referencedColumns: ["unit_id"];
          },
        ];
      };
      vw_employee: {
        Row: {
          cargo: string | null;
          company_id: string | null;
          company_name: string | null;
          employee_id: string | null;
          gestor_name: string | null;
          hired_on: string | null;
          name: string | null;
          registration_number: string | null;
          status: string | null;
          tenant_id: string | null;
          unit_id: string | null;
          unit_name: string | null;
        };
        Relationships: [
          {
            foreignKeyName: "employee_unit_id_fkey";
            columns: ["unit_id"];
            isOneToOne: false;
            referencedRelation: "vw_unit";
            referencedColumns: ["unit_id"];
          },
        ];
      };
      vw_payroll_summary: {
        Row: {
          colaboradores: number | null;
          company_id: string | null;
          month: number | null;
          tenant_id: string | null;
          total_descontos: number | null;
          total_encargos: number | null;
          total_proventos: number | null;
          unit_id: string | null;
          year: number | null;
        };
        Relationships: [
          {
            foreignKeyName: "payroll_entry_unit_id_fkey";
            columns: ["unit_id"];
            isOneToOne: false;
            referencedRelation: "vw_unit";
            referencedColumns: ["unit_id"];
          },
        ];
      };
      vw_unit: {
        Row: {
          active: boolean | null;
          code: string | null;
          company_id: string | null;
          company_name: string | null;
          name: string | null;
          tenant_id: string | null;
          timezone: string | null;
          unit_id: string | null;
        };
        Relationships: [];
      };
    };
    Functions: {
      fn_data_freshness: {
        Args: { p_stale_after_minutes?: number };
        Returns: {
          age_minutes: number;
          entity: string;
          is_stale: boolean;
          last_sync_at: string;
          tenant_id: string;
        }[];
      };
      fn_detection_health: {
        Args: { p_backfill_max_age_hours?: number };
        Returns: {
          backfill_age_hours: number;
          backfill_overdue: boolean;
          incremental_age_minutes: number;
          last_backfill_at: string;
          last_incremental_at: string;
          tenant_id: string;
        }[];
      };
      fn_kpi_period: {
        Args: {
          p_ate: string;
          p_company_id?: string;
          p_de: string;
          p_department_id?: string;
          p_manager_id?: string;
          p_unit_id?: string;
        };
        Returns: {
          colaboradores_afetados: number;
          eventos: number;
          eventos_pendentes_ciclo: number;
          minutes_abs: number;
          minutes_excedente: number;
          minutes_faltante: number;
          unidades_afetadas: number;
        }[];
      };
      fn_pending_justification: {
        Args: {
          p_ate: string;
          p_de: string;
          p_department_id?: string;
          p_manager_id?: string;
          p_unit_id?: string;
        };
        Returns: {
          detected_at: string;
          deviation_event_id: string;
          employee_id: string;
          employee_name: string;
          minutes: number;
          reference_date: string;
          type: string;
          type_description: string;
          unit_id: string;
          unit_name: string;
        }[];
      };
      fn_ranking_by_employee: {
        Args: {
          p_ate: string;
          p_company_id?: string;
          p_de: string;
          p_department_id?: string;
          p_limite?: number;
          p_manager_id?: string;
          p_unit_id?: string;
        };
        Returns: {
          employee_id: string;
          employee_name: string;
          eventos: number;
          minutes_abs: number;
          unit_name: string;
        }[];
      };
      fn_ranking_by_manager: {
        Args: {
          p_ate: string;
          p_company_id?: string;
          p_de: string;
          p_department_id?: string;
          p_limite?: number;
          p_unit_id?: string;
        };
        Returns: {
          colaboradores: number;
          eventos: number;
          manager_id: string;
          manager_name: string;
          minutes_abs: number;
          unidades: number;
        }[];
      };
      fn_ranking_by_unit: {
        Args: {
          p_ate: string;
          p_company_id?: string;
          p_de: string;
          p_department_id?: string;
          p_limite?: number;
          p_manager_id?: string;
        };
        Returns: {
          colaboradores: number;
          eventos: number;
          minutes_abs: number;
          unit_id: string;
          unit_name: string;
        }[];
      };
      fn_recurrence: {
        Args: {
          p_ate: string;
          p_de: string;
          p_department_id?: string;
          p_manager_id?: string;
          p_min_dias?: number;
          p_unit_id?: string;
        };
        Returns: {
          dias_com_desvio: number;
          employee_id: string;
          employee_name: string;
          eventos: number;
          unit_name: string;
        }[];
      };
      fn_whatsapp_readiness: {
        Args: never;
        Returns: {
          official: boolean;
          provider: string;
          ready: boolean;
          rules_blocked: number;
          templates_approved: number;
          templates_total: number;
          tenant_id: string;
        }[];
      };
    };
    Enums: {
      [_ in never]: never;
    };
    CompositeTypes: {
      [_ in never]: never;
    };
  };
};

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">;

type DefaultSchema = DatabaseWithoutInternals[Extract<
  keyof Database,
  "public"
>];

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R;
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R;
      }
      ? R
      : never
    : never;

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    keyof DefaultSchema["Tables"] | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I;
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I;
      }
      ? I
      : never
    : never;

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    keyof DefaultSchema["Tables"] | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U;
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U;
      }
      ? U
      : never
    : never;

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    keyof DefaultSchema["Enums"] | { schema: keyof DatabaseWithoutInternals },
  EnumName extends (DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never) = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never;

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends (PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never) = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never;

export const Constants = {
  graphql_public: {
    Enums: {},
  },
  public: {
    Enums: {},
  },
} as const;
