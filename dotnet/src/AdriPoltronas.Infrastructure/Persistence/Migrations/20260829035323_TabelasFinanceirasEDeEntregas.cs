using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AdriPoltronas.Infrastructure.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class TabelasFinanceirasEDeEntregas : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "entregas_agendadas",
                columns: table => new
                {
                    id = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    cliente_id = table.Column<int>(type: "INTEGER", nullable: false),
                    cliente_nome = table.Column<string>(type: "TEXT", maxLength: 120, nullable: false),
                    data_entrega = table.Column<string>(type: "TEXT", nullable: false),
                    hora_entrega = table.Column<string>(type: "TEXT", maxLength: 5, nullable: false),
                    descricao = table.Column<string>(type: "TEXT", maxLength: 1000, nullable: false),
                    status = table.Column<string>(type: "TEXT", nullable: false),
                    criado_em = table.Column<string>(type: "TEXT", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_entregas_agendadas", x => x.id);
                });

            migrationBuilder.CreateTable(
                name: "notificacoes_lidas",
                columns: table => new
                {
                    chave = table.Column<string>(type: "TEXT", maxLength: 120, nullable: false),
                    lida_em = table.Column<string>(type: "TEXT", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_notificacoes_lidas", x => x.chave);
                });

            migrationBuilder.CreateTable(
                name: "pagamentos",
                columns: table => new
                {
                    id = table.Column<int>(type: "INTEGER", nullable: false),
                    cliente_id = table.Column<int>(type: "INTEGER", nullable: false),
                    cliente_nome = table.Column<string>(type: "TEXT", maxLength: 120, nullable: false),
                    valor = table.Column<double>(type: "REAL", nullable: false),
                    descricao = table.Column<string>(type: "TEXT", maxLength: 1000, nullable: false),
                    data_vencimento = table.Column<string>(type: "TEXT", nullable: false),
                    data_pagamento = table.Column<string>(type: "TEXT", nullable: false),
                    tipo_pagamento = table.Column<string>(type: "TEXT", nullable: false),
                    status = table.Column<string>(type: "TEXT", nullable: false),
                    criado_em = table.Column<string>(type: "TEXT", nullable: false),
                    asaas_payment_id = table.Column<string>(type: "TEXT", nullable: false),
                    pix_payload = table.Column<string>(type: "TEXT", nullable: false),
                    pix_qr_code = table.Column<string>(type: "TEXT", nullable: false),
                    boleto_url = table.Column<string>(type: "TEXT", nullable: false),
                    nosso_numero = table.Column<string>(type: "TEXT", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_pagamentos", x => x.id);
                });

            migrationBuilder.CreateIndex(
                name: "ix_entregas_status_data",
                table: "entregas_agendadas",
                columns: new[] { "status", "data_entrega" });

            migrationBuilder.CreateIndex(
                name: "ix_pagamentos_cliente",
                table: "pagamentos",
                column: "cliente_id");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "entregas_agendadas");

            migrationBuilder.DropTable(
                name: "notificacoes_lidas");

            migrationBuilder.DropTable(
                name: "pagamentos");
        }
    }
}
